"""
API do CRM local da ferramenta de prospecção.

Uso:
    py app.py              # Windows
    python3.11 app.py      # macOS/Linux
A API sobe em http://localhost:5000. A interface (React) roda em
http://localhost:5173 - use iniciar.bat (Windows) ou iniciar.sh (macOS/Linux)
na raiz pra subir os dois juntos.

O código está dividido por responsabilidade:
    rotas_leads.py      - CRM dos leads do Google Maps + disparo da busca
    rotas_instagram.py  - CRM dos leads do Instagram + disparo da análise
    rotas_analytics.py  - métricas, funis, meta semanal, follow-ups do dia
    rotas_config.py     - chaves de IA, proxies, templates de mensagem
    ia.py               - provedores de IA e fallback unificado
    jobs.py             - jobs de background (scraper/análise) + persistência
    db.py               - conexão, configurações e backup do banco
    processar.py        - pipeline do CSV do scraper + schema/migrações
"""

import logging
import os
import sqlite3
import threading
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException

import paths

load_dotenv()

paths.garantir_pastas_de_dados()

APP_DIR = paths.DIR_RECURSOS
PASTA_LOGS = paths.DIR_DADOS / "logs"
PASTA_LOGS.mkdir(parents=True, exist_ok=True)
_handler_log = RotatingFileHandler(
    PASTA_LOGS / "prospeccao.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
)
_handler_log.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.getLogger().addHandler(_handler_log)
# nível configurável via .env: PROSPECCAO_LOG_LEVEL=DEBUG|INFO|WARNING|ERROR
_nivel_log = os.environ.get("PROSPECCAO_LOG_LEVEL", "INFO").upper()
logging.getLogger().setLevel(getattr(logging, _nivel_log, logging.INFO))
logger = logging.getLogger(__name__)

import db
import jobs
import processar
import rotas_analytics
import rotas_config
import rotas_instagram
import rotas_leads

app = Flask(__name__)
app.register_blueprint(rotas_leads.bp)
app.register_blueprint(rotas_instagram.bp)
app.register_blueprint(rotas_analytics.bp)
app.register_blueprint(rotas_config.bp)


@app.errorhandler(Exception)
def tratar_erro_generico(erro):
    if isinstance(erro, HTTPException):
        return erro  # 404, 405 etc. devem chegar como são, não virar erro interno
    logger.exception("erro não tratado numa rota")
    return jsonify({"erro": "Ocorreu um erro interno. Veja detalhes em logs/prospeccao.log."}), 500


# ---------------------------------------------------------------------------
# Servir o frontend buildado (produção/empacotado)
#
# Em dev o Vite (porta 5173) continua sendo a interface, com proxy pra cá.
# Empacotado (ou rodando só o backend com o build feito), o próprio Flask serve
# o dist/ na MESMA origem da API - como o frontend chama tudo por /api/*
# relativo, nenhuma configuração de URL é necessária.
# ---------------------------------------------------------------------------

DIR_FRONTEND_DIST = (
    paths.caminho_recurso("frontend_dist")
    if paths.EMPACOTADO
    else Path(__file__).parent.parent / "frontend" / "dist"
)


@app.route("/", defaults={"caminho": "index.html"})
@app.route("/<path:caminho>")
def servir_frontend(caminho):
    if caminho.startswith("api/"):
        abort(404)  # rota de API inexistente não deve devolver HTML
    if not DIR_FRONTEND_DIST.exists():
        return (
            jsonify({"erro": "Interface não encontrada. Em dev, use http://localhost:5173 (iniciar.bat/iniciar.sh)."}),
            404,
        )
    if (DIR_FRONTEND_DIST / caminho).is_file():
        return send_from_directory(DIR_FRONTEND_DIST, caminho)
    # SPA fallback: qualquer rota do React Router devolve o index.html
    return send_from_directory(DIR_FRONTEND_DIST, "index.html")


def preparar_banco_no_startup():
    """Garante que o schema esteja atualizado assim que o app sobe, mesmo que o
    usuário ainda não tenha rodado nenhuma busca nesta instalação."""
    conexao = sqlite3.connect(db.CAMINHO_BANCO, timeout=10)
    try:
        processar.preparar_banco(conexao)
    finally:
        conexao.close()


preparar_banco_no_startup()
jobs.marcar_jobs_interrompidos()
db.migrar_chaves_para_keyring()


def escolher_porta(preferida=5000):
    """Usa a porta preferida se estiver livre; senão pede uma porta livre ao SO."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", preferida))
            return preferida
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _abrir_navegador(porta):
    webbrowser.open(f"http://127.0.0.1:{porta}")


if __name__ == "__main__":
    modo_dev = os.environ.get("PROSPECCAO_DEBUG", "false").lower() == "true"
    if modo_dev:
        # dev com auto-reload do Flask, comportamento de sempre
        app.run(debug=True, port=5000)
    else:
        porta = escolher_porta(5000)
        # anuncia a porta pra quem iniciou o processo (shell do app de desktop lê
        # o stdout; o arquivo cobre quem preferir ler do disco). Empacotado sem
        # console, sys.stdout pode ser None - o arquivo vira a fonte da verdade.
        try:
            print(f"LISTENING_ON={porta}", flush=True)
        except Exception:
            pass
        paths.caminho_dados("porta.txt", criar_pai=True).write_text(str(porta), encoding="utf-8")
        logger.info("servindo em http://127.0.0.1:%s", porta)

        # empacotado não tem script de inicialização: o próprio app abre a interface - exceto
        # quando quem subiu o backend foi o shell de desktop (Electron), que tem
        # janela própria e seta PROSPECTOS_NO_BROWSER=1
        if paths.EMPACOTADO and os.environ.get("PROSPECTOS_NO_BROWSER") != "1":
            threading.Timer(1.0, _abrir_navegador, args=(porta,)).start()

        # waitress: servidor WSGI de produção (o dev server do Flask não é pra isso)
        from waitress import serve

        serve(app, host="127.0.0.1", port=porta, threads=8)
