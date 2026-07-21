"""Caminhos centrais do app.

Autoridade dos paths:
1. PROSPECTOS_* explícita (variável de ambiente)
2. Fallback nativo por plataforma

No modo desktop, o Electron resolve os paths e passa via PROSPECTOS_*.
O backend usa fallback próprio quando executado sem Electron.

Quatro diretórios raiz:

  DIR_DADOS     dados graváveis (banco, backups, saídas, sessões)
  DIR_LOGS      logs
  DIR_TEMP      temporários
  DIR_RECURSOS  read-only (código, frontend buildado, binários)
"""

import os
import sys
import tempfile
from pathlib import Path

# PyInstaller define sys.frozen no executável gerado
EMPACOTADO = bool(getattr(sys, "frozen", False))

_DIR_FONTE = Path(__file__).parent


# ── helpers de validação ──────────────────────────────────────────────────

def _val(var: str) -> str | None:
    """Retorna o valor da env var ou None se vazia/ausente."""
    val = os.environ.get(var)
    if val is not None and val.strip():
        return val.strip()
    return None


def _abs(caminho: str | Path) -> Path:
    """Expande ~ e converte para path absoluto."""
    p = Path(os.path.expanduser(str(caminho)))
    if p.is_absolute():
        return p
    return p.absolute()


# ── defaults por plataforma ───────────────────────────────────────────────

def _default_cache_dir() -> Path:
    if sys.platform == "win32":
        local_app_data = _val("LOCALAPPDATA")
        return _abs(Path(local_app_data or "~") / "ProspectOS" / "cache")
    if sys.platform == "darwin":
        return _abs(Path.home() / "Library" / "Caches" / "ProspectOS")
    xdg = _val("XDG_CACHE_HOME")
    if xdg:
        return _abs(Path(xdg) / "ProspectOS")
    return _abs(Path.home() / ".cache" / "ProspectOS")


def _default_data_dir() -> Path:
    if sys.platform == "win32":
        base = _val("APPDATA")
        return _abs(Path(base or "~") / "ProspectOS")
    if sys.platform == "darwin":
        return _abs(Path.home() / "Library" / "Application Support" / "ProspectOS")
    xdg = _val("XDG_DATA_HOME")
    if xdg:
        return _abs(Path(xdg) / "ProspectOS")
    return _abs(Path.home() / ".local" / "share" / "ProspectOS")


def _default_log_dir() -> Path:
    if sys.platform == "darwin":
        return _abs(Path.home() / "Library" / "Logs" / "ProspectOS")
    if sys.platform == "win32":
        return _default_data_dir() / "logs"
    xdg = _val("XDG_STATE_HOME")
    if xdg:
        return _abs(Path(xdg) / "ProspectOS" / "logs")
    return _abs(Path.home() / ".local" / "state" / "ProspectOS" / "logs")


def _default_temp_dir() -> Path:
    tmpdir_base = _val("TMPDIR") or tempfile.gettempdir()
    return _abs(Path(tmpdir_base) / "ProspectOS")


def _default_resource_dir() -> Path:
    if EMPACOTADO:
        return _abs(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)))
    return _DIR_FONTE


# ── constantes resolvidas ─────────────────────────────────────────────────

DIR_DADOS: Path = _abs(_val("PROSPECTOS_DATA_DIR") or _default_data_dir())
DIR_LOGS: Path = _abs(_val("PROSPECTOS_LOG_DIR") or _default_log_dir())
DIR_TEMP: Path = _abs(_val("PROSPECTOS_TEMP_DIR") or _default_temp_dir())
DIR_RECURSOS: Path = _abs(_val("PROSPECTOS_RESOURCE_DIR") or _default_resource_dir())
DIR_CACHE: Path = _abs(_val("PROSPECTOS_CACHE_DIR") or _default_cache_dir())


# ── helpers públicos ──────────────────────────────────────────────────────

def caminho_recurso(*partes: str) -> Path:
    """Caminho de um recurso read-only distribuído junto com o app."""
    return DIR_RECURSOS.joinpath(*partes)


def caminho_dados(*partes: str, criar_pai: bool = False) -> Path:
    """Caminho de um arquivo/pasta de dados do usuário (sempre gravável).

    Com criar_pai=True, garante que o diretório pai exista antes de devolver —
    útil pra quem vai abrir o arquivo pra escrita logo em seguida.
    """
    caminho = DIR_DADOS.joinpath(*partes)
    if criar_pai:
        caminho.parent.mkdir(parents=True, exist_ok=True)
    return caminho


def caminho_log(*partes: str, criar_pai: bool = False) -> Path:
    """Caminho de um arquivo/pasta de log."""
    caminho = DIR_LOGS.joinpath(*partes)
    if criar_pai:
        caminho.parent.mkdir(parents=True, exist_ok=True)
    return caminho


def caminho_temp(*partes: str, criar_pai: bool = False) -> Path:
    """Caminho de um arquivo/pasta temporário."""
    caminho = DIR_TEMP.joinpath(*partes)
    if criar_pai:
        caminho.parent.mkdir(parents=True, exist_ok=True)
    return caminho


def garantir_pastas_de_dados() -> None:
    """Cria a estrutura de pastas graváveis (chamado no startup do app)."""
    DIR_DADOS.mkdir(parents=True, exist_ok=True)
    DIR_LOGS.mkdir(parents=True, exist_ok=True)
    for sub in ("backups", "saidas", Path("instagram") / "sessao", Path("instagram") / "comentarios"):
        (DIR_DADOS / sub).mkdir(parents=True, exist_ok=True)
