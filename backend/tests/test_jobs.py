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

import subprocess
import sys
import time
from pathlib import Path

import pytest

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
        assert "google-maps-scraper" in msg

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
# Plataforma — nomes do scraper e Node resolvidos sem assumir Windows
# ---------------------------------------------------------------------------

class TestPlataformaScraper:
    def test_nome_do_scraper_no_windows(self, monkeypatch):
        monkeypatch.setattr(jobs.sys, "platform", "win32")
        assert jobs.nome_executavel_scraper() == "google-maps-scraper.exe"

    def test_nome_do_scraper_no_macos(self, monkeypatch):
        monkeypatch.setattr(jobs.sys, "platform", "darwin")
        assert jobs.nome_executavel_scraper() == "google-maps-scraper"

    def test_node_no_macos_vem_do_path_quando_nao_ha_config(self, monkeypatch):
        monkeypatch.setattr(jobs.sys, "platform", "darwin")
        monkeypatch.setattr(jobs.db, "obter_config", lambda _chave: None)
        monkeypatch.setattr(jobs, "caminho_recurso", lambda *partes: Path("/app").joinpath(*partes))
        monkeypatch.setattr(jobs.shutil, "which", lambda nome: "/opt/homebrew/bin/node" if nome == "node" else None)
        assert jobs.caminho_node_padrao({}) == "/opt/homebrew/bin/node"

    def test_node_no_windows_mantem_fallback_classico(self, monkeypatch):
        monkeypatch.setattr(jobs.sys, "platform", "win32")
        monkeypatch.setattr(jobs.db, "obter_config", lambda _chave: None)
        monkeypatch.setattr(jobs, "caminho_recurso", lambda *partes: Path("C:/app").joinpath(*partes))
        monkeypatch.setattr(jobs.shutil, "which", lambda _nome: None)
        assert jobs.caminho_node_padrao({}) == r"C:\Program Files\nodejs\node.exe"

    def test_driver_playwright_respeita_variavel_de_ambiente(self):
        assert jobs.caminho_driver_playwright_padrao({"PLAYWRIGHT_DRIVER_PATH": "/tmp/pw"}) == "/tmp/pw"

    def test_driver_playwright_usa_pasta_local_quando_existe(self, tmp_path, monkeypatch):
        driver = tmp_path / ".playwright-driver"
        (driver / "package").mkdir(parents=True)
        (driver / "package" / "cli.js").write_text("", encoding="utf-8")
        monkeypatch.setattr(jobs, "caminho_recurso", lambda *partes: tmp_path.joinpath(*partes))
        assert jobs.caminho_driver_playwright_padrao({}) == str(driver)

    def test_driver_playwright_none_quando_nao_configurado(self, tmp_path, monkeypatch):
        monkeypatch.setattr(jobs, "caminho_recurso", lambda *partes: tmp_path.joinpath(*partes))
        assert jobs.caminho_driver_playwright_padrao({}) is None


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
            sys.executable, "-c",
            "import sys; [print(f'linha {i}') for i in range(3)]; sys.exit(0)",
        ]
        linhas_recebidas = []
        returncode, stderr = jobs.rodar_scraper_com_progresso(
            comando=comando, cwd=None, env=None, timeout_segundos=30,
            callback_linha=linhas_recebidas.append,
        )
        assert returncode == 0
        assert len(linhas_recebidas) == 3
        assert "linha 0" in linhas_recebidas[0]

    def test_returncode_de_erro_e_propagado(self):
        comando = [sys.executable, "-c", "import sys; sys.exit(2)"]
        returncode, _ = jobs.rodar_scraper_com_progresso(
            comando=comando, cwd=None, env=None, timeout_segundos=30,
        )
        assert returncode == 2

    def test_stderr_e_capturado(self):
        comando = [
            sys.executable, "-c",
            "import sys; print('erro fatal', file=sys.stderr); sys.exit(1)",
        ]
        returncode, stderr = jobs.rodar_scraper_com_progresso(
            comando=comando, cwd=None, env=None, timeout_segundos=30,
        )
        assert returncode == 1
        assert "erro fatal" in stderr

    def test_timeout_mata_o_processo_e_lanca(self):
        # O timeout é checado dentro do loop de leitura do stdout, a cada linha —
        # que é como o scraper real se comporta (emite eventos de progresso o tempo
        # todo). Um processo que emite linhas continuamente e nunca termina deve ser
        # cortado pelo timeout e levantar TimeoutExpired.
        comando = [
            sys.executable, "-c",
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
