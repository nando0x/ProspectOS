"""Caminhos centrais do app: onde ficam os recursos (read-only) e os dados (graváveis).

Dois modos de execução:

- **Fonte** (clone do repo, `py app.py`): tudo fica na pasta do projeto, como sempre
  foi — nada muda para quem desenvolve ou roda os testes.
- **Empacotado** (PyInstaller, `sys.frozen`): o código e os recursos viram um bundle
  read-only (possivelmente em Program Files), então os dados do usuário (banco,
  backups, saídas, sessão do Instagram) PRECISAM ir para uma pasta gravável —
  `%APPDATA%\\ProspectOS` no Windows ou `XDG_DATA_HOME/ProspectOS` no Linux.
  Sem essa separação, o app instalado não consegue gravar nada e um update apagaria
  os leads.

**Docker / Linux nativo:** defina `PROSPECTOS_DATA_DIR` (ex.: `/data`) para separar
dados graváveis do código da imagem.

Regra prática para os outros módulos:
- arquivo que o app só LÊ e vem junto do código (scraper, os .py do instagram,
  o build do frontend) → `caminho_recurso(...)`
- arquivo que o app ESCREVE (leads.db, backups/, saidas/, queries.txt, logs/,
  instagram/sessao/, instagram/comentarios/) → `caminho_dados(...)`
"""

import os
import sys
from pathlib import Path

# PyInstaller define sys.frozen no executável gerado
EMPACOTADO = bool(getattr(sys, "frozen", False))

_DIR_FONTE = Path(__file__).parent


def _resolver_dir_dados():
    """Pasta gravável: env explícito > empacotado por SO > pasta do backend (dev)."""
    if os.environ.get("PROSPECTOS_DATA_DIR"):
        return Path(os.environ["PROSPECTOS_DATA_DIR"])

    if EMPACOTADO:
        if sys.platform == "win32":
            return Path(os.environ.get("APPDATA", str(Path.home()))) / "ProspectOS"
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
        return base / "ProspectOS"

    return _DIR_FONTE


if EMPACOTADO:
    # --onedir: recursos adicionados via --add-data ficam em sys._MEIPASS
    # (na prática a pasta _internal ao lado do .exe)
    DIR_RECURSOS = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    DIR_RECURSOS = _DIR_FONTE

DIR_DADOS = _resolver_dir_dados()


def caminho_recurso(*partes):
    """Caminho de um recurso read-only distribuído junto com o app."""
    return DIR_RECURSOS.joinpath(*partes)


def caminho_dados(*partes, criar_pai=False):
    """Caminho de um arquivo/pasta de dados do usuário (sempre gravável).

    Com criar_pai=True, garante que o diretório pai exista antes de devolver —
    útil pra quem vai abrir o arquivo pra escrita logo em seguida.
    """
    caminho = DIR_DADOS.joinpath(*partes)
    if criar_pai:
        caminho.parent.mkdir(parents=True, exist_ok=True)
    return caminho


def garantir_pastas_de_dados():
    """Cria a estrutura de pastas graváveis (chamado no startup do app)."""
    DIR_DADOS.mkdir(parents=True, exist_ok=True)
    for sub in ("backups", "saidas", "logs", Path("instagram") / "sessao", Path("instagram") / "comentarios"):
        (DIR_DADOS / sub).mkdir(parents=True, exist_ok=True)
