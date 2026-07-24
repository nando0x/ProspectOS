"""
Testes de jobs.py — o motor de background (busca no Maps + análise de Instagram).

Cobre as partes testáveis sem rodar o scraper de verdade nem acessar rede:
- funções puras (tradução de erro, zoom por raio, parse de progresso do scraper);
- o lock de concorrência que impede duas buscas ao mesmo tempo;
- a persistência do ciclo de vida do job na tabela `jobs`;
- os callbacks de progresso ao vivo (estado em memória + tabela);
- rodar_scraper_com_progresso com um processo fake (sucesso, erro, timeout).

Banco SQLite temporário via monkeypatch em db.CAMINHO_BANCO, nunca o leads.db real.
Rodar com: py -m pytest tests/test_jobs.py
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Cursor/alguns ambientes apontam sys.executable para o binário do IDE, não o Python.
PYTHON = shutil.which("python3") or "/usr/bin/python3"

sys.path.insert(0, str(Path(__file__).parent.parent))

import db
import jobs
import processar


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Banco temporário isolado, com o schema real aplicado."""
    caminho = tmp_path / "leads_teste.db"
    monkeypatch.setattr(db, "CAMINHO_BANCO", caminho)
    conexao = db.conectar()
    try:
        processar.preparar_banco(conexao)
    finally:
        conexao.close()
    return caminho


@pytest.fixture(autouse=True)
def resetar_estado():
    """Cada teste começa com o estado global limpo (é dict de módulo, compartilhado)."""
    jobs.estado_busca["rodando"] = False
    jobs.estado_instagram["rodando"] = False
    jobs._job_id_busca = None
    jobs._job_id_instagram = None
    yield
    jobs.estado_busca["rodando"] = False
    jobs.estado_instagram["rodando"] = False


def _ler_job(job_id):
    conexao = db.conectar()
    try:
        conexao.row_factory = __import__("sqlite3").Row
        return conexao.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        conexao.close()


# ---------------------------------------------------------------------------
# traduzir_erro_scraper — mensagem crua vira algo que o usuário leigo entende
# ---------------------------------------------------------------------------

class TestTraduzirErroScraper:
    def test_erro_de_driver_playwright(self):
        msg = jobs.traduzir_erro_scraper("Error: could not install driver", 1)
        assert "navegador interno" in msg
        assert "Node.js" in msg

    def test_erro_menciona_playwright(self):
        msg = jobs.traduzir_erro_scraper("playwright install failed", 1)
        assert "navegador interno" in msg

    def test_arquivo_nao_encontrado(self):
        msg = jobs.traduzir_erro_scraper("no such file or directory", 127)
        assert jobs.nome_binario_scraper() in msg

    def test_timeout_deadline(self):
        msg = jobs.traduzir_erro_scraper("context deadline exceeded", 1)
        assert "demorou demais" in msg

    def test_erro_generico_cai_no_fallback_com_codigo(self):
        msg = jobs.traduzir_erro_scraper("algo estranho aconteceu", 42)
        assert "código 42" in msg
        assert "prospeccao.log" in msg

    def test_stderr_none_nao_quebra(self):
        # returncode != 0 com stderr vazio deve cair no fallback sem lançar exceção
        msg = jobs.traduzir_erro_scraper(None, 3)
        assert "código 3" in msg

    def test_case_insensitive(self):
        # a saída do binário pode vir com maiúsculas
        msg = jobs.traduzir_erro_scraper("Could Not Install Driver", 1)
        assert "navegador interno" in msg


# ---------------------------------------------------------------------------
# nome_binario_scraper e resolver_caminho_node — portabilidade Linux/Windows
# ---------------------------------------------------------------------------

class TestPortabilidadeScraper:
    def test_nome_binario_windows(self, monkeypatch):
        monkeypatch.setattr(jobs.sys, "platform", "win32")
        assert jobs.nome_binario_scraper() == "google-maps-scraper.exe"

    def test_nome_binario_linux(self, monkeypatch):
        monkeypatch.setattr(jobs.sys, "platform", "linux")
        assert jobs.nome_binario_scraper() == "google-maps-scraper"

    def test_resolver_node_via_which_no_linux(self, monkeypatch):
        monkeypatch.setattr(jobs.sys, "platform", "linux")
        monkeypatch.setattr(jobs.db, "obter_config", lambda _chave: None)
        monkeypatch.setattr(jobs.shutil, "which", lambda _nome: "/usr/bin/node")
        assert jobs.resolver_caminho_node({}) == "/usr/bin/node"

    def test_resolver_node_prioriza_config(self, monkeypatch):
        monkeypatch.setattr(jobs.db, "obter_config", lambda _chave: "/custom/node")
        assert jobs.resolver_caminho_node({}) == "/custom/node"

    def test_resolver_node_prioriza_env(self, monkeypatch):
        monkeypatch.setattr(jobs.db, "obter_config", lambda _chave: None)
        assert jobs.resolver_caminho_node({"PLAYWRIGHT_NODEJS_PATH": "/env/node"}) == "/env/node"


# ---------------------------------------------------------------------------
# zoom_para_raio — raio maior exige zoom menor, sempre dentro de [8, 17]
# ---------------------------------------------------------------------------

class TestZoomParaRaio:
    def test_raio_1km(self):
        assert jobs.zoom_para_raio(1000) == 15

    def test_raio_5km(self):
        assert jobs.zoom_para_raio(5000) == 13

    def test_raio_50km(self):
        assert jobs.zoom_para_raio(50000) == 9

    def test_raio_maior_reduz_o_zoom(self):
        assert jobs.zoom_para_raio(20000) < jobs.zoom_para_raio(2000)

    def test_nunca_passa_do_teto(self):
        # raio minúsculo não pode estourar o zoom máximo (17)
        assert jobs.zoom_para_raio(1) <= 17

    def test_nunca_passa_do_piso(self):
        # raio gigante não pode ir abaixo do zoom mínimo (8)
        assert jobs.zoom_para_raio(10_000_000) >= 8


# ---------------------------------------------------------------------------
# _processar_linha_de_progresso_scraper — lê o stdout JSON e alimenta os contadores
# ---------------------------------------------------------------------------

class TestProcessarLinhaDeProgresso:
    def setup_method(self):
        jobs.estado_busca["empresas_encontradas"] = 0
        jobs.estado_busca["empresas_processadas"] = 0

    def test_job_finished_incrementa_processadas(self):
        jobs._processar_linha_de_progresso_scraper('{"message": "job finished"}')
        assert jobs.estado_busca["empresas_processadas"] == 1

    def test_places_found_soma_encontradas(self):
        jobs._processar_linha_de_progresso_scraper('{"message": "12 places found"}')
        assert jobs.estado_busca["empresas_encontradas"] == 12

    def test_places_found_acumula(self):
        jobs._processar_linha_de_progresso_scraper('{"message": "5 places found"}')
        jobs._processar_linha_de_progresso_scraper('{"message": "3 places found"}')
        assert jobs.estado_busca["empresas_encontradas"] == 8

    def test_linha_nao_json_e_ignorada(self):
        # log solto do binário (não-JSON) não pode quebrar nem mexer nos contadores
        jobs._processar_linha_de_progresso_scraper("INFO: iniciando navegador")
        assert jobs.estado_busca["empresas_encontradas"] == 0
        assert jobs.estado_busca["empresas_processadas"] == 0

    def test_linha_vazia_e_ignorada(self):
        jobs._processar_linha_de_progresso_scraper("   ")
        assert jobs.estado_busca["empresas_processadas"] == 0

    def test_mensagem_desconhecida_nao_altera_contadores(self):
        jobs._processar_linha_de_progresso_scraper('{"message": "outra coisa qualquer"}')
        assert jobs.estado_busca["empresas_encontradas"] == 0
        assert jobs.estado_busca["empresas_processadas"] == 0


# ---------------------------------------------------------------------------
# Concorrência — o lock que impede duas buscas simultâneas
# ---------------------------------------------------------------------------

class TestReservaDeBusca:
    def test_primeira_reserva_passa(self):
        assert jobs.tentar_reservar_busca() is True
        assert jobs.estado_busca["rodando"] is True

    def test_segunda_reserva_e_bloqueada(self):
        assert jobs.tentar_reservar_busca() is True
        assert jobs.tentar_reservar_busca() is False  # já tem uma rodando

    def test_liberar_permite_nova_reserva(self):
        jobs.tentar_reservar_busca()
        jobs.liberar_busca()
        assert jobs.estado_busca["rodando"] is False
        assert jobs.tentar_reservar_busca() is True

    def test_instagram_tem_lock_independente_da_busca(self):
        # reservar a busca do Maps não pode bloquear a análise do Instagram
        assert jobs.tentar_reservar_busca() is True
        assert jobs.tentar_reservar_analise_instagram() is True

    def test_segunda_reserva_instagram_e_bloqueada(self):
        assert jobs.tentar_reservar_analise_instagram() is True
        assert jobs.tentar_reservar_analise_instagram() is False


# ---------------------------------------------------------------------------
# Persistência do ciclo de vida do job na tabela `jobs`
# ---------------------------------------------------------------------------

class TestPersistenciaDoJob:
    def test_registrar_inicio_cria_linha_rodando(self, banco):
        job_id = jobs._registrar_inicio_job("busca_maps")
        linha = _ler_job(job_id)
        assert linha["tipo"] == "busca_maps"
        assert linha["status"] == "rodando"
        assert linha["iniciado_em"]

    def test_registrar_inicio_guarda_referencia(self, banco):
        job_id = jobs._registrar_inicio_job("analise_instagram", referencia_id=99)
        assert _ler_job(job_id)["referencia_id"] == 99

    def test_atualizar_job_grava_etapa_e_progresso(self, banco):
        job_id = jobs._registrar_inicio_job("busca_maps")
        jobs._atualizar_job(job_id, etapa="verificando_sites", progresso_atual=3, progresso_total=10)
        linha = _ler_job(job_id)
        assert linha["etapa"] == "verificando_sites"
        assert linha["progresso_atual"] == 3
        assert linha["progresso_total"] == 10

    def test_atualizar_job_id_none_e_no_op(self, banco):
        # não deve lançar exceção quando não há job ativo
        jobs._atualizar_job(None, etapa="x")

    def test_finalizar_job_marca_status_e_data_fim(self, banco):
        job_id = jobs._registrar_inicio_job("busca_maps")
        jobs._finalizar_job(job_id, "concluido", "Busca concluída: 5 leads")
        linha = _ler_job(job_id)
        assert linha["status"] == "concluido"
        assert linha["mensagem"] == "Busca concluída: 5 leads"
        assert linha["finalizado_em"]

    def test_finalizar_sem_mensagem_preserva_a_existente(self, banco):
        job_id = jobs._registrar_inicio_job("busca_maps")
        jobs._atualizar_job(job_id, mensagem="mensagem original")
        jobs._finalizar_job(job_id, "erro", None)  # None não sobrescreve (COALESCE)
        linha = _ler_job(job_id)
        assert linha["status"] == "erro"
        assert linha["mensagem"] == "mensagem original"

    def test_finalizar_job_id_none_e_no_op(self, banco):
        jobs._finalizar_job(None, "concluido")


class TestMarcarJobsInterrompidos:
    def test_job_rodando_vira_interrompido(self, banco):
        job_id = jobs._registrar_inicio_job("busca_maps")
        jobs.marcar_jobs_interrompidos()
        linha = _ler_job(job_id)
        assert linha["status"] == "interrompido"
        assert linha["finalizado_em"]

    def test_job_ja_concluido_nao_e_tocado(self, banco):
        job_id = jobs._registrar_inicio_job("busca_maps")
        jobs._finalizar_job(job_id, "concluido", "ok")
        jobs.marcar_jobs_interrompidos()
        assert _ler_job(job_id)["status"] == "concluido"

    def test_sem_jobs_rodando_nao_quebra(self, banco):
        jobs.marcar_jobs_interrompidos()  # banco vazio, não deve lançar


# ---------------------------------------------------------------------------
# Callback de progresso da verificação de sites (estado em memória + tabela)
# ---------------------------------------------------------------------------

class TestCallbackProgressoVerificacao:
    def test_atualiza_estado_em_memoria(self, banco):
        jobs._job_id_busca = jobs._registrar_inicio_job("busca_maps")
        jobs._callback_progresso_verificacao(2, 8, "Padaria do João")
        assert jobs.estado_busca["etapa"] == "verificando_sites"
        assert jobs.estado_busca["empresas_processadas"] == 2
        assert jobs.estado_busca["empresas_encontradas"] == 8
        assert "Padaria do João" in jobs.estado_busca["mensagem"]

    def test_persiste_progresso_no_job(self, banco):
        jobs._job_id_busca = jobs._registrar_inicio_job("busca_maps")
        jobs._callback_progresso_verificacao(4, 10, "Empresa X")
        linha = _ler_job(jobs._job_id_busca)
        assert linha["progresso_atual"] == 4
        assert linha["progresso_total"] == 10
        assert linha["etapa"] == "verificando_sites"


# ---------------------------------------------------------------------------
# rodar_scraper_com_progresso — com um processo Python fake no lugar do .exe
# ---------------------------------------------------------------------------

class TestRodarScraperComProgresso:
    def test_sucesso_le_stdout_linha_a_linha(self):
        # processo fake que imprime 3 linhas e sai com código 0
        comando = [
            PYTHON, "-c",
            "import sys; [print(f'linha {i}') for i in range(3)]; sys.exit(0)",
        ]
        linhas_recebidas = []
        returncode, stderr, killed_idle = jobs.rodar_scraper_com_progresso(
            comando=comando, cwd=None, env=None, timeout_segundos=30,
            callback_linha=linhas_recebidas.append,
        )
        assert returncode == 0
        assert killed_idle is False
        assert len(linhas_recebidas) == 3
        assert "linha 0" in linhas_recebidas[0]

    def test_returncode_de_erro_e_propagado(self):
        comando = [PYTHON, "-c", "import sys; sys.exit(2)"]
        returncode, _, killed_idle = jobs.rodar_scraper_com_progresso(
            comando=comando, cwd=None, env=None, timeout_segundos=30,
        )
        assert returncode == 2
        assert killed_idle is False

    def test_stderr_e_capturado(self):
        comando = [
            PYTHON, "-c",
            "import sys; print('erro fatal', file=sys.stderr); sys.exit(1)",
        ]
        returncode, stderr, killed_idle = jobs.rodar_scraper_com_progresso(
            comando=comando, cwd=None, env=None, timeout_segundos=30,
        )
        assert returncode == 1
        assert killed_idle is False
        assert "erro fatal" in stderr

    def test_idle_timeout_mata_processo_que_para_de_emitir_stdout(self):
        # imprime uma linha e depois fica vivo sem stdout (simula o hang do gosom)
        comando = [
            PYTHON, "-c",
            "import time\n"
            "print('progresso', flush=True)\n"
            "time.sleep(9999)",
        ]
        inicio = time.monotonic()
        returncode, _, killed_idle = jobs.rodar_scraper_com_progresso(
            comando=comando, cwd=None, env=None, timeout_segundos=60,
            idle_timeout_segundos=1,
            callback_linha=lambda _linha: None,
        )
        assert killed_idle is True
        assert returncode != 0  # morto por sinal (ex.: -9 no Linux)
        assert time.monotonic() - inicio < 10

    def test_timeout_mata_o_processo_e_lanca(self):
        # O timeout é checado dentro do loop de leitura do stdout, a cada linha —
        # que é como o scraper real se comporta (emite eventos de progresso o tempo
        # todo). Um processo que emite linhas continuamente e nunca termina deve ser
        # cortado pelo timeout e levantar TimeoutExpired.
        comando = [
            PYTHON, "-c",
            "import time\n"
            "while True:\n"
            "    print('progresso', flush=True)\n"
            "    time.sleep(0.05)",
        ]
        inicio = time.monotonic()
        with pytest.raises(subprocess.TimeoutExpired):
            jobs.rodar_scraper_com_progresso(
                comando=comando, cwd=None, env=None, timeout_segundos=1,
                callback_linha=lambda _linha: None,
            )
        # cortou perto de 1s, muito antes de rodar pra sempre
        assert time.monotonic() - inicio < 15


class TestCsvBrutoTemDados:
    def test_arquivo_com_dados(self, tmp_path):
        arquivo = tmp_path / "bruto.csv"
        arquivo.write_text("header\nlinha1\n", encoding="utf-8")
        assert jobs._csv_bruto_tem_dados(arquivo) is True

    def test_so_cabecalho(self, tmp_path):
        arquivo = tmp_path / "bruto.csv"
        arquivo.write_text("header\n", encoding="utf-8")
        assert jobs._csv_bruto_tem_dados(arquivo) is False

    def test_arquivo_inexistente(self, tmp_path):
        assert jobs._csv_bruto_tem_dados(tmp_path / "nao_existe.csv") is False


class TestContarLinhasDadosCsv:
    def test_conta_linhas_de_dados(self, tmp_path):
        arquivo = tmp_path / "bruto.csv"
        arquivo.write_text("h1,h2\na,b\nc,d\n", encoding="utf-8")
        assert jobs._contar_linhas_dados_csv(arquivo) == 2

    def test_arquivo_vazio(self, tmp_path):
        arquivo = tmp_path / "bruto.csv"
        arquivo.write_text("", encoding="utf-8")
        assert jobs._contar_linhas_dados_csv(arquivo) == 0


class TestAtualizarProgressoCsv:
    def setup_method(self):
        jobs.estado_busca["empresas_encontradas"] = 0
        jobs.estado_busca["empresas_processadas"] = 0
        jobs.estado_busca["etapa"] = "scraping"
        jobs.estado_busca["mensagem"] = ""

    def test_atualiza_contadores_e_mensagem(self, tmp_path, banco):
        arquivo = tmp_path / "bruto.csv"
        arquivo.write_text("header\nlinha1\nlinha2\n", encoding="utf-8")
        jobs._job_id_busca = jobs._registrar_inicio_job("busca_maps")

        contagem = jobs._atualizar_progresso_csv(arquivo)

        assert contagem == 2
        assert jobs.estado_busca["empresas_encontradas"] == 2
        assert jobs.estado_busca["empresas_processadas"] == 2
        assert "2 empresa(s) capturada(s)" in jobs.estado_busca["mensagem"]
        linha = _ler_job(jobs._job_id_busca)
        assert linha["progresso_atual"] == 2
        assert linha["progresso_total"] == 2

    def test_monotono_nao_regride(self, tmp_path):
        arquivo = tmp_path / "bruto.csv"
        arquivo.write_text("header\nlinha1\n", encoding="utf-8")
        jobs.estado_busca["empresas_encontradas"] = 5
        jobs.estado_busca["empresas_processadas"] = 5

        jobs._atualizar_progresso_csv(arquivo)

        assert jobs.estado_busca["empresas_encontradas"] == 5
        assert jobs.estado_busca["empresas_processadas"] == 5

    def test_csv_vazio_nao_altera(self, tmp_path):
        arquivo = tmp_path / "bruto.csv"
        arquivo.write_text("header\n", encoding="utf-8")

        assert jobs._atualizar_progresso_csv(arquivo) == 0
        assert jobs.estado_busca["empresas_encontradas"] == 0


class TestObterStatusBusca:
    def test_rodando_inclui_progresso_da_memoria(self):
        jobs.estado_busca.update({
            "rodando": True,
            "mensagem": "Buscando...",
            "etapa": "scraping",
            "empresas_encontradas": 10,
            "empresas_processadas": 4,
            "area_atual": 0,
            "total_areas": 0,
        })

        status = jobs.obter_status_busca()

        assert status["rodando"] is True
        assert status["progresso_atual"] == 4
        assert status["progresso_total"] == 10

    def test_fallback_ultimo_job_quando_mensagem_vazia(self, banco):
        jobs.estado_busca.update({
            "rodando": False,
            "mensagem": "",
            "etapa": "",
            "empresas_encontradas": 0,
            "empresas_processadas": 0,
            "area_atual": 0,
            "total_areas": 0,
        })
        job_id = jobs._registrar_inicio_job("busca_maps")
        jobs._finalizar_job(job_id, "concluido", "Busca concluída: 3 leads")

        status = jobs.obter_status_busca()

        assert status["mensagem"] == "Busca concluída: 3 leads"

    def test_job_rodando_no_banco_sem_memoria_e_interrompido(self, banco):
        jobs.estado_busca.update({
            "rodando": False,
            "mensagem": "",
            "etapa": "",
            "empresas_encontradas": 0,
            "empresas_processadas": 0,
            "area_atual": 0,
            "total_areas": 0,
        })
        jobs._registrar_inicio_job("busca_maps")

        status = jobs.obter_status_busca()

        assert status["rodando"] is False
        assert "interrompida" in status["mensagem"].lower()


class TestExecutarScraperRecuperacaoCsv:
    def test_erro_com_csv_valido_continua(self, tmp_path, monkeypatch):
        arquivo = tmp_path / "bruto.csv"
        arquivo.write_text("header\ndados\n", encoding="utf-8")
        monkeypatch.setattr(
            jobs,
            "rodar_scraper_com_progresso",
            lambda **kwargs: (-9, "killed", True),
        )
        monkeypatch.setattr(jobs, "caminho_recurso", lambda nome: tmp_path / nome)
        monkeypatch.setattr(jobs, "DIR_DADOS", tmp_path)
        monkeypatch.setattr(jobs.db, "obter_config", lambda _chave: None)

        assert jobs._executar_scraper(arquivo, {}) is None

    def test_erro_sem_csv_retorna_mensagem(self, tmp_path, monkeypatch):
        arquivo = tmp_path / "bruto.csv"
        monkeypatch.setattr(
            jobs,
            "rodar_scraper_com_progresso",
            lambda **kwargs: (1, "falhou", False),
        )
        monkeypatch.setattr(jobs, "caminho_recurso", lambda nome: tmp_path / nome)
        monkeypatch.setattr(jobs, "DIR_DADOS", tmp_path)
        monkeypatch.setattr(jobs.db, "obter_config", lambda _chave: None)

        erro = jobs._executar_scraper(arquivo, {})
        assert erro is not None
        assert "código 1" in erro
