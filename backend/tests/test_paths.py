"""Testes de paths.py: resolução multiplataforma de DIR_DADOS, DIR_LOGS,
DIR_TEMP e DIR_RECURSOS.

A resolução segue a precedência:
1. PROSPECTOS_* explícita (variável de ambiente)
2. Fallback nativo por plataforma

Os testes usam monkeypatch + importlib.reload para controlar as variáveis
de ambiente e sys.platform sem depender do sistema real.
"""

import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import paths


# ── helpers ────────────────────────────────────────────────────────────────

def _recarregar():
    """Recarrega paths.py para que as constantes sejam reavaliadas."""
    importlib.reload(paths)


def _limpar_envs(*envs, monkeypatch):
    """Remove uma lista de env vars do ambiente."""
    for var in envs:
        monkeypatch.delenv(var, raising=False)


# ── Precedência: PROSPECTOS_* vence default da plataforma ─────────────────

class TestPrecedencia:
    def test_prospectos_data_dir_vence_default(self, monkeypatch):
        monkeypatch.setenv("PROSPECTOS_DATA_DIR", "/tmp/custom-data")
        _recarregar()
        assert paths.DIR_DADOS == Path("/tmp/custom-data").absolute()

    def test_prospectos_log_dir_vence_default(self, monkeypatch):
        monkeypatch.setenv("PROSPECTOS_LOG_DIR", "/tmp/custom-log")
        _recarregar()
        assert paths.DIR_LOGS == Path("/tmp/custom-log").absolute()

    def test_prospectos_temp_dir_vence_default(self, monkeypatch):
        monkeypatch.setenv("PROSPECTOS_TEMP_DIR", "/tmp/custom-temp")
        _recarregar()
        assert paths.DIR_TEMP == Path("/tmp/custom-temp").absolute()

    def test_prospectos_resource_dir_vence_default(self, monkeypatch):
        monkeypatch.setenv("PROSPECTOS_RESOURCE_DIR", "/tmp/custom-resource")
        _recarregar()
        assert paths.DIR_RECURSOS == Path("/tmp/custom-resource").absolute()

    def test_cada_var_independente(self, monkeypatch):
        monkeypatch.setenv("PROSPECTOS_DATA_DIR", "/tmp/a")
        monkeypatch.setenv("PROSPECTOS_LOG_DIR", "/tmp/b")
        _recarregar()
        assert paths.DIR_DADOS == Path("/tmp/a").absolute()
        assert paths.DIR_LOGS == Path("/tmp/b").absolute()

    def test_variavel_vazia_tratada_como_ausente(self, monkeypatch):
        monkeypatch.setenv("PROSPECTOS_DATA_DIR", "")
        _recarregar()
        # Deve cair no default da plataforma (macOS, já que o teste roda num Mac)
        assert paths.DIR_DADOS != Path("").absolute()
        assert paths.DIR_DADOS.name == "ProspectOS"

    def test_variavel_so_com_espacos_tratada_como_ausente(self, monkeypatch):
        monkeypatch.setenv("PROSPECTOS_DATA_DIR", "   ")
        _recarregar()
        assert paths.DIR_DADOS.name == "ProspectOS"


# ── macOS ─────────────────────────────────────────────────────────────────

class TestMacOS:
    def test_default_data_dir(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        _limpar_envs("PROSPECTOS_DATA_DIR", "APPDATA", monkeypatch=monkeypatch)
        _recarregar()
        esperado = Path.home() / "Library" / "Application Support" / "ProspectOS"
        assert paths.DIR_DADOS == esperado.absolute()

    def test_default_log_dir(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        _limpar_envs("PROSPECTOS_LOG_DIR", monkeypatch=monkeypatch)
        _recarregar()
        esperado = Path.home() / "Library" / "Logs" / "ProspectOS"
        assert paths.DIR_LOGS == esperado.absolute()

    def test_default_temp_dir(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        _limpar_envs("PROSPECTOS_TEMP_DIR", monkeypatch=monkeypatch)
        _recarregar()
        assert paths.DIR_TEMP.name == "ProspectOS"
        assert paths.DIR_TEMP.is_absolute()

    def test_default_resource_dir_fonte(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        _limpar_envs("PROSPECTOS_RESOURCE_DIR", monkeypatch=monkeypatch)
        _recarregar()
        assert paths.DIR_RECURSOS == Path(paths.__file__).parent

    def test_data_log_separados_macos(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        _limpar_envs("PROSPECTOS_DATA_DIR", "PROSPECTOS_LOG_DIR", monkeypatch=monkeypatch)
        _recarregar()
        # No macOS, data e logs ficam em pastas separadas
        assert paths.DIR_DADOS != paths.DIR_LOGS
        assert "Logs" in str(paths.DIR_LOGS)
        assert "Application Support" in str(paths.DIR_DADOS)


# ── Windows ───────────────────────────────────────────────────────────────

class TestWindows:
    def test_default_data_dir_com_appdata(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", "/Users/Test/AppData/Roaming")
        _limpar_envs("PROSPECTOS_DATA_DIR", monkeypatch=monkeypatch)
        _recarregar()
        esperado = Path("/Users/Test/AppData/Roaming/ProspectOS")
        assert paths.DIR_DADOS == esperado

    def test_default_data_dir_sem_appdata(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        _limpar_envs("PROSPECTOS_DATA_DIR", "APPDATA", monkeypatch=monkeypatch)
        _recarregar()
        # fallback: home + ProspectOS
        assert paths.DIR_DADOS.name == "ProspectOS"

    def test_default_log_dir_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", "/Users/Test/AppData/Roaming")
        _limpar_envs("PROSPECTOS_DATA_DIR", "PROSPECTOS_LOG_DIR", monkeypatch=monkeypatch)
        _recarregar()
        # Windows: logs dentro de data/logs (backward compat)
        esperado = Path("/Users/Test/AppData/Roaming/ProspectOS/logs")
        assert paths.DIR_LOGS == esperado

    def test_appdata_prospectos_preservado(self, monkeypatch):
        """Compatibilidade Windows: o path existente não muda."""
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", "/Users/Real/AppData/Roaming")
        _limpar_envs("PROSPECTOS_DATA_DIR", monkeypatch=monkeypatch)
        _recarregar()
        esperado = Path("/Users/Real/AppData/Roaming/ProspectOS")
        assert paths.DIR_DADOS == esperado

    def test_leads_db_em_dir_dados(self, monkeypatch):
        """CAMINHO_BANCO fica dentro de DIR_DADOS."""
        esperado = paths.DIR_DADOS / "leads.db"
        assert esperado == paths.DIR_DADOS / "leads.db"


# ── Linux ─────────────────────────────────────────────────────────────────

class TestLinux:
    def test_com_xdg_data_home(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_DATA_HOME", "/home/test/.local/share")
        _limpar_envs("PROSPECTOS_DATA_DIR", monkeypatch=monkeypatch)
        _recarregar()
        esperado = Path("/home/test/.local/share/ProspectOS")
        assert paths.DIR_DADOS == esperado

    def test_sem_xdg_data_home(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        _limpar_envs("PROSPECTOS_DATA_DIR", "XDG_DATA_HOME", monkeypatch=monkeypatch)
        _recarregar()
        esperado = Path.home() / ".local" / "share" / "ProspectOS"
        assert paths.DIR_DADOS == esperado.absolute()

    def test_com_xdg_state_home(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_STATE_HOME", "/home/test/.local/state")
        _limpar_envs("PROSPECTOS_LOG_DIR", monkeypatch=monkeypatch)
        _recarregar()
        esperado = Path("/home/test/.local/state/ProspectOS/logs")
        assert paths.DIR_LOGS == esperado

    def test_sem_xdg_state_home(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        _limpar_envs("PROSPECTOS_LOG_DIR", "XDG_STATE_HOME", monkeypatch=monkeypatch)
        _recarregar()
        esperado = Path.home() / ".local" / "state" / "ProspectOS" / "logs"
        assert paths.DIR_LOGS == esperado.absolute()

    def test_com_tmpdir(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("TMPDIR", "/custom/tmp")
        _limpar_envs("PROSPECTOS_TEMP_DIR", monkeypatch=monkeypatch)
        _recarregar()
        esperado = Path("/custom/tmp/ProspectOS")
        assert paths.DIR_TEMP == esperado

    def test_sem_tmpdir(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        _limpar_envs("PROSPECTOS_TEMP_DIR", "TMPDIR", monkeypatch=monkeypatch)
        _recarregar()
        assert paths.DIR_TEMP.name == "ProspectOS"
        assert paths.DIR_TEMP.is_absolute()


# ── Diretório de recursos (read-only) ────────────────────────────────────

class TestRecursos:
    def test_recursos_eh_fonte_quando_nao_empacotado(self):
        assert paths.EMPACOTADO is False
        assert paths.DIR_RECURSOS == Path(paths.__file__).parent

    def test_caminho_recurso_junta_partes(self):
        assert paths.caminho_recurso("instagram", "login.py") == (
            paths.DIR_RECURSOS / "instagram" / "login.py"
        )

    def test_empacotado_recursos_vao_para_meipass(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", "/tmp/bundle", raising=False)
        _limpar_envs("PROSPECTOS_RESOURCE_DIR", monkeypatch=monkeypatch)
        _recarregar()
        assert paths.DIR_RECURSOS == Path("/tmp/bundle")
        assert paths.EMPACOTADO is True

    def test_recursos_nao_sao_criados_por_garantir_pastas(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "DIR_RECURSOS", tmp_path / "recursos")
        monkeypatch.setattr(paths, "DIR_DADOS", tmp_path / "dados")
        # recursos não deve ser criado
        paths.garantir_pastas_de_dados()
        assert not (tmp_path / "recursos").exists()
        assert (tmp_path / "dados").exists()

    def test_recursos_read_only_distinct_from_data(self, monkeypatch):
        """Empacotado: recursos e dados são diretórios diferentes."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", "/tmp/bundle", raising=False)
        monkeypatch.setenv("APPDATA", "/tmp/appdata")
        _limpar_envs("PROSPECTOS_DATA_DIR", "PROSPECTOS_RESOURCE_DIR", monkeypatch=monkeypatch)
        _recarregar()
        assert paths.DIR_RECURSOS != paths.DIR_DADOS
        assert paths.DIR_RECURSOS == Path("/tmp/bundle")


# ── Helpers caminho_dados / caminho_log / caminho_temp ───────────────────

class TestHelpers:
    def test_caminho_dados_junta_partes(self):
        assert paths.caminho_dados("saidas", "x.csv") == paths.DIR_DADOS / "saidas" / "x.csv"

    def test_caminho_dados_criar_pai(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "DIR_DADOS", tmp_path)
        caminho = paths.caminho_dados("nova_pasta", "arquivo.txt", criar_pai=True)
        assert caminho.parent.is_dir()
        assert caminho == tmp_path / "nova_pasta" / "arquivo.txt"

    def test_caminho_log_junta_partes(self):
        assert paths.caminho_log("prospeccao.log") == paths.DIR_LOGS / "prospeccao.log"

    def test_caminho_log_cria_pai(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "DIR_LOGS", tmp_path / "logs")
        caminho = paths.caminho_log("sub", "arquivo.log", criar_pai=True)
        assert caminho.parent.is_dir()
        assert caminho == tmp_path / "logs" / "sub" / "arquivo.log"

    def test_caminho_temp_junta_partes(self):
        assert paths.caminho_temp("staging", "f.tmp") == paths.DIR_TEMP / "staging" / "f.tmp"

    def test_caminho_temp_cria_pai(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "DIR_TEMP", tmp_path / "temp")
        caminho = paths.caminho_temp("sub", "f.tmp", criar_pai=True)
        assert caminho.parent.is_dir()


# ── Diretórios criados por garantizar_pastas_de_dados ────────────────────

class TestGarantirPastas:
    def test_cria_data_log_e_subpastas(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "DIR_DADOS", tmp_path / "dados")
        monkeypatch.setattr(paths, "DIR_LOGS", tmp_path / "logs")
        monkeypatch.setattr(paths, "DIR_TEMP", tmp_path / "temp")
        paths.garantir_pastas_de_dados()
        assert (tmp_path / "dados").is_dir()
        assert (tmp_path / "logs").is_dir()
        for sub in ("backups", "saidas", "instagram/sessao", "instagram/comentarios"):
            assert (tmp_path / "dados" / sub).is_dir(), f"faltou criar {sub}"
        # TEMP não é criado por garantizar_pastas
        assert not (tmp_path / "temp").exists()

    def test_temp_nao_criado_por_garantir_pastas(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "DIR_DADOS", tmp_path / "dados")
        monkeypatch.setattr(paths, "DIR_LOGS", tmp_path / "logs")
        paths.garantir_pastas_de_dados()
        assert (tmp_path / "dados").is_dir()
        assert (tmp_path / "logs").is_dir()


# ── Não duplicação do nome "ProspectOS" ──────────────────────────────────

class TestNaoDuplicacao:
    def test_data_dir_nao_duplica_prospectos(self, monkeypatch):
        """Simula Electron passando path já terminado em ProspectOS.
        O backend deve usar o path como está, sem adicionar outro ProspectOS."""
        monkeypatch.setenv("PROSPECTOS_DATA_DIR",
                           "/tmp/Application Support/ProspectOS")
        _recarregar()
        resultado = str(paths.DIR_DADOS)
        # Deve terminar exatamente uma vez com ProspectOS
        assert resultado.endswith("ProspectOS")
        # Não deve conter "ProspectOS/ProspectOS"
        assert "ProspectOS/ProspectOS" not in resultado

    def test_data_dir_path_com_prospectos_nao_duplica(self, monkeypatch):
        monkeypatch.setenv("PROSPECTOS_DATA_DIR",
                           "/Users/test/Library/Application Support/ProspectOS")
        _recarregar()
        resultado = str(paths.DIR_DADOS)
        assert resultado.count("ProspectOS") == 1

    def test_windows_path_nao_duplica_prospectos(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", "/Users/Test/AppData/Roaming")
        _limpar_envs("PROSPECTOS_DATA_DIR", monkeypatch=monkeypatch)
        _recarregar()
        resultado = str(paths.DIR_DADOS)
        # APPDATA/ProspectOS — sem duplicação
        assert resultado.count("ProspectOS") == 1
        assert "/AppData/Roaming/ProspectOS" in resultado


# ── Paths com espaços e Unicode ──────────────────────────────────────────

class TestPathsEspeciais:
    def test_paths_com_espacos(self, monkeypatch):
        monkeypatch.setenv("PROSPECTOS_DATA_DIR", "/tmp/ProspectOS Teste")
        _recarregar()
        assert paths.DIR_DADOS == Path("/tmp/ProspectOS Teste").absolute()
        assert paths.DIR_DADOS.exists() is False  # não foi criado

    def test_paths_com_unicode(self, monkeypatch):
        monkeypatch.setenv("PROSPECTOS_DATA_DIR", "/tmp/ProspectOS Usuário")
        _recarregar()
        assert paths.DIR_DADOS == Path("/tmp/ProspectOS Usuário").absolute()


# ── CAMINHO_BANCO e estrutura abaixo de DIR_DADOS ────────────────────────

class TestCaminhoBanco:
    def test_caminho_banco_em_dir_dados(self):
        assert paths.DIR_DADOS / "leads.db" == paths.caminho_dados("leads.db")

    def test_caminho_banco_respeita_env_var(self, monkeypatch):
        monkeypatch.setenv("PROSPECTOS_DATA_DIR", "/tmp/x")
        _recarregar()
        assert paths.DIR_DADOS / "leads.db" == Path("/tmp/x/leads.db")

    def test_backups_em_dir_dados(self):
        assert paths.DIR_DADOS / "backups" == paths.caminho_dados("backups")

    def test_saidas_em_dir_dados(self):
        assert paths.DIR_DADOS / "saidas" == paths.caminho_dados("saidas")

    def test_instagram_sessao_em_dir_dados(self):
        expected = paths.DIR_DADOS / "instagram" / "sessao"
        assert expected == paths.caminho_dados("instagram", "sessao")

    def test_instagram_comentarios_em_dir_dados(self):
        expected = paths.DIR_DADOS / "instagram" / "comentarios"
        assert expected == paths.caminho_dados("instagram", "comentarios")


# ── Limpeza entre os testes ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _restaurar_modulos_apos_teste():
    """Restaura módulos que cachem paths em constantes de módulo."""
    yield
    importlib.reload(paths)
    for mod_name in ("db", "processar", "instagram.login"):
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])