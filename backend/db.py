"""Acesso ao banco (SQLite), configurações persistidas e backup.

Os módulos de rotas devem sempre acessar CAMINHO_BANCO via `db.CAMINHO_BANCO`
(atributo do módulo, não import direto do nome) - é isso que permite aos testes
apontarem tudo para um banco temporário com um único monkeypatch.
"""

import logging
import shutil
import sqlite3
import os
from datetime import datetime
from pathlib import Path

from paths import DIR_DADOS, DIR_RECURSOS

logger = logging.getLogger(__name__)

# APP_DIR aponta pros RECURSOS (código, scraper .exe) - continua exportado porque
# jobs.py e outros o usam. Dados graváveis (banco, backups) vêm de DIR_DADOS:
# na fonte é a mesma pasta de sempre; empacotado vira %APPDATA%\ProspectOS.
APP_DIR = DIR_RECURSOS
CAMINHO_BANCO = DIR_DADOS / "leads.db"
PASTA_BACKUPS = DIR_DADOS / "backups"
MAX_BACKUPS_MANTIDOS = 20

CHAVES_CONFIG_VALIDAS = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "pagespeed": "PAGESPEED_API_KEY",
    "places": "PLACES_API_KEY",
}

# Chaves que são segredo de verdade: ficam no cofre de credenciais do sistema
# (Windows Credential Manager, via keyring/DPAPI), nunca em plaintext no
# leads.db - o banco entra nos backups automáticos, o cofre não.
CHAVES_SECRETAS = set(CHAVES_CONFIG_VALIDAS)
_SERVICO_KEYRING = "ProspectOS"


def _keyring_obter(chave):
    try:
        import keyring
        return keyring.get_password(_SERVICO_KEYRING, chave)
    except Exception:
        logger.debug("keyring indisponível ao ler a chave %s", chave)
        return None


def _keyring_salvar(chave, valor):
    try:
        import keyring
        keyring.set_password(_SERVICO_KEYRING, chave, valor)
        return True
    except Exception:
        logger.exception("keyring indisponível ao salvar a chave %s - usando o banco como fallback", chave)
        return False


def _keyring_apagar(chave):
    try:
        import keyring
        keyring.delete_password(_SERVICO_KEYRING, chave)
    except Exception:
        pass  # a chave pode simplesmente não existir no cofre


def conectar():
    conexao = sqlite3.connect(CAMINHO_BANCO, timeout=10)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA journal_mode=WAL")
    conexao.execute("PRAGMA busy_timeout=10000")
    conexao.execute("PRAGMA foreign_keys=ON")
    return conexao


def linha_para_dict(linha):
    return dict(linha)


def obter_config(chave, default=None):
    """Lê uma configuração. Ordem de prioridade:
    1. cofre de credenciais (só chaves secretas, gravadas pela UI)
    2. tabela `configuracoes` (configs comuns; e chaves legadas ainda não migradas)
    3. variável de ambiente / .env"""
    if chave in CHAVES_SECRETAS:
        valor = _keyring_obter(chave)
        if valor:
            return valor

    conexao = conectar()
    try:
        linha = conexao.execute(
            "SELECT valor FROM configuracoes WHERE chave = ?", (chave,)
        ).fetchone()
    finally:
        conexao.close()

    if linha and linha["valor"]:
        return linha["valor"]

    chave_env = CHAVES_CONFIG_VALIDAS.get(chave, chave)
    return os.environ.get(chave_env, default)


def _apagar_config_db(chave):
    conexao = conectar()
    try:
        conexao.execute("DELETE FROM configuracoes WHERE chave = ?", (chave,))
        conexao.commit()
    finally:
        conexao.close()


def salvar_config(chave, valor):
    # chave secreta vai pro cofre; qualquer cópia plaintext antiga sai do banco.
    # Se o keyring estiver indisponível, degrada pro comportamento antigo (banco).
    if chave in CHAVES_SECRETAS and _keyring_salvar(chave, valor):
        _apagar_config_db(chave)
        return

    conexao = conectar()
    try:
        conexao.execute(
            """
            INSERT INTO configuracoes (chave, valor, atualizado_em) VALUES (?, ?, ?)
            ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, atualizado_em = excluded.atualizado_em
            """,
            (chave, valor, datetime.now().isoformat(timespec="seconds")),
        )
        conexao.commit()
    finally:
        conexao.close()


def migrar_chaves_para_keyring():
    """Migração de segurança (roda no startup): move chaves de API que ficaram
    em plaintext na tabela `configuracoes` para o cofre de credenciais do sistema
    e apaga a cópia do banco. Idempotente; se o keyring estiver indisponível,
    não faz nada (as chaves continuam funcionando pelo banco)."""
    conexao = conectar()
    try:
        linhas = conexao.execute(
            "SELECT chave, valor FROM configuracoes WHERE chave IN ({}) AND valor IS NOT NULL AND valor != ''".format(
                ",".join("?" for _ in CHAVES_SECRETAS)
            ),
            sorted(CHAVES_SECRETAS),
        ).fetchall()
    finally:
        conexao.close()

    for linha in linhas:
        if _keyring_salvar(linha["chave"], linha["valor"]):
            _apagar_config_db(linha["chave"])
            logger.info("chave %s migrada do banco para o cofre de credenciais", linha["chave"])


def fazer_backup_banco():
    """Copia o leads.db pra pasta backups/ antes de mudanças em massa. Mantém só
    os N mais recentes pra não crescer sem limite."""
    if not CAMINHO_BANCO.exists():
        return

    PASTA_BACKUPS.mkdir(exist_ok=True)
    carimbo = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    destino = PASTA_BACKUPS / f"leads_{carimbo}.db"
    try:
        shutil.copy2(CAMINHO_BANCO, destino)
        logger.info("backup do banco criado em %s", destino)
    except OSError:
        logger.exception("não foi possível criar backup do banco")
        return

    arquivos = sorted(PASTA_BACKUPS.glob("leads_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for antigo in arquivos[MAX_BACKUPS_MANTIDOS:]:
        antigo.unlink(missing_ok=True)
