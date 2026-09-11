"""Testes de paths.py e da infra de servir o app (porta dinâmica + SPA fallback).

paths.py é a fundação do app empacotado: decide onde ficam recursos (read-only)
e dados (graváveis). Errar isso significa app instalado que não grava nada ou
update que apaga leads - por isso os dois modos são testados explicitamente.
"""

import importlib
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import app as app_module
import paths


# ---------------------------------------------------------------------------
# Modo fonte (clone/dev): tudo na pasta do projeto, como sempre foi
# ---------------------------------------------------------------------------

class TestModoFonte:
    @pytest.fixture(autouse=True)
    def _sem_prospectos_data_dir(self, monkeypatch):
        monkeypatch.delenv("PROSPECTOS_DATA_DIR", raising=False)
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        importlib.reload(paths)

    def test_nao_empacotado(self):
        assert paths.EMPACOTADO is False

    def test_recursos_e_dados_sao_a_pasta_do_backend(self):
        pasta_backend = Path(paths.__file__).parent
        assert paths.DIR_RECURSOS == pasta_backend
        assert paths.DIR_DADOS == pasta_backend

    def test_caminho_recurso_junta_partes(self):
        assert paths.caminho_recurso("instagram", "login.py") == (
            paths.DIR_RECURSOS / "instagram" / "login.py"
        )

    def test_caminho_dados_junta_partes(self):
        assert paths.caminho_dados("saidas", "x.csv") == paths.DIR_DADOS / "saidas" / "x.csv"

    def test_caminho_dados_criar_pai(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "DIR_DADOS", tmp_path)
        caminho = paths.caminho_dados("nova_pasta", "arquivo.txt", criar_pai=True)
        assert caminho.parent.is_dir()
        assert caminho == tmp_path / "nova_pasta" / "arquivo.txt"

    def test_garantir_pastas_de_dados_cria_estrutura(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "DIR_DADOS", tmp_path / "dados")
        paths.garantir_pastas_de_dados()
        for sub in ("backups", "saidas", "logs", "instagram/sessao", "instagram/comentarios"):
            assert (tmp_path / "dados" / sub).is_dir(), f"faltou criar {sub}"


# ---------------------------------------------------------------------------
# Modo empacotado (PyInstaller): recursos no bundle, dados em %APPDATA%
# ---------------------------------------------------------------------------

class TestModoEmpacotado:
    @pytest.fixture(autouse=True)
    def _sem_prospectos_data_dir(self, monkeypatch):
        monkeypatch.delenv("PROSPECTOS_DATA_DIR", raising=False)

    def test_dados_vao_para_appdata_e_recursos_para_o_bundle(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
        monkeypatch.setattr(sys, "platform", "win32", raising=False)
        monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
        try:
            recarregado = importlib.reload(paths)
            assert recarregado.EMPACOTADO is True
            assert recarregado.DIR_RECURSOS == tmp_path / "bundle"
            assert recarregado.DIR_DADOS == tmp_path / "appdata" / "ProspectOS"
            # a separação é o que garante que um update não apaga os leads
            assert recarregado.DIR_RECURSOS != recarregado.DIR_DADOS
        finally:
            monkeypatch.undo()
            importlib.reload(paths)  # restaura o módulo pro modo fonte

    def test_estado_restaurado_apos_o_teste_anterior(self):
        # sanidade: o reload do finally devolveu o módulo ao modo fonte
        assert paths.EMPACOTADO is False


# ---------------------------------------------------------------------------
# Docker / Linux: PROSPECTOS_DATA_DIR e XDG_DATA_HOME
# ---------------------------------------------------------------------------

class TestModoLinuxDocker:
    def test_prospectos_data_dir_tem_prioridade(self, tmp_path, monkeypatch):
        dados = tmp_path / "data"
        monkeypatch.setenv("PROSPECTOS_DATA_DIR", str(dados))
        try:
            recarregado = importlib.reload(paths)
            assert recarregado.DIR_DADOS == dados
            assert recarregado.DIR_RECURSOS == Path(paths.__file__).parent
        finally:
            monkeypatch.delenv("PROSPECTOS_DATA_DIR", raising=False)
            importlib.reload(paths)

    def test_empacotado_linux_usa_xdg_data_home(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
        monkeypatch.setattr(sys, "platform", "linux", raising=False)
        monkeypatch.delenv("PROSPECTOS_DATA_DIR", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        try:
            recarregado = importlib.reload(paths)
            assert recarregado.DIR_DADOS == tmp_path / "xdg" / "ProspectOS"
        finally:
            monkeypatch.undo()
            importlib.reload(paths)


# ---------------------------------------------------------------------------
# Porta dinâmica
# ---------------------------------------------------------------------------

class TestEscolherPorta:
    def test_porta_livre_usa_a_preferida(self):
        # pega uma porta livre qualquer pra usar como "preferida"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            porta_livre = sock.getsockname()[1]
        assert app_module.escolher_porta(porta_livre) == porta_livre

    def test_porta_ocupada_cai_pra_outra(self):
        with socket.socket() as ocupada:
            ocupada.bind(("127.0.0.1", 0))
            porta_ocupada = ocupada.getsockname()[1]
            escolhida = app_module.escolher_porta(porta_ocupada)
            assert escolhida != porta_ocupada
            assert 0 < escolhida < 65536


# ---------------------------------------------------------------------------
# Flask servindo o frontend (SPA fallback)
# ---------------------------------------------------------------------------

@pytest.fixture
def cliente_com_dist(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>ProspectOS</body></html>", encoding="utf-8")
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("console.log('oi')", encoding="utf-8")
    monkeypatch.setattr(app_module, "DIR_FRONTEND_DIST", dist)
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as cliente:
        yield cliente


class TestServirFrontend:
    def test_raiz_devolve_index(self, cliente_com_dist):
        resposta = cliente_com_dist.get("/")
        assert resposta.status_code == 200
        assert b"ProspectOS" in resposta.data

    def test_arquivo_estatico_e_servido(self, cliente_com_dist):
        resposta = cliente_com_dist.get("/assets/app.js")
        assert resposta.status_code == 200
        assert b"console.log" in resposta.data

    def test_rota_spa_faz_fallback_pro_index(self, cliente_com_dist):
        # rota do React Router (não existe como arquivo) deve devolver o index
        resposta = cliente_com_dist.get("/tarefas")
        assert resposta.status_code == 200
        assert b"ProspectOS" in resposta.data

    def test_api_inexistente_da_404_e_nao_html(self, cliente_com_dist):
        resposta = cliente_com_dist.get("/api/rota-que-nao-existe")
        assert resposta.status_code == 404
        assert b"ProspectOS" not in resposta.data

    def test_sem_dist_da_404_amigavel(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "DIR_FRONTEND_DIST", tmp_path / "nao-existe")
        app_module.app.config["TESTING"] = True
        with app_module.app.test_client() as cliente:
            resposta = cliente.get("/")
            assert resposta.status_code == 404
            assert "5173" in resposta.get_json()["erro"]
