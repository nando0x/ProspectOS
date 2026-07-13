"""
Interface visual (CRM local) da ferramenta de prospecção.

Uso:
    py app.py
Depois abra http://localhost:5000 no navegador.
"""

import io
import csv
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request
from flask_cors import CORS

import processar

load_dotenv()

APP_DIR = Path(__file__).parent
sys.path.insert(0, str(APP_DIR / "instagram"))
CAMINHO_BANCO = APP_DIR / "leads.db"
PASTA_LOGS = APP_DIR / "logs"
PASTA_BACKUPS = APP_DIR / "backups"
STATUS_VALIDOS = {"novo", "contatado", "respondeu", "fechou", "recusou", "ignorado"}
STATUS_QUE_ENCERRAM_FOLLOWUP = {"fechou", "recusou", "ignorado"}
MAX_BACKUPS_MANTIDOS = 20
TIMEOUT_SCRAPER_SEGUNDOS = 900  # 15 minutos - nunca deve travar pra sempre
MAX_CARACTERES_OBSERVACOES = 5000
MAX_CARACTERES_TAGS = 500
MAX_LINHAS_QUERIES_BUSCA = 50
MAX_CARACTERES_POR_LINHA_QUERY = 200
MAX_CARACTERES_SUGESTAO_DM = 2000
MAX_CARACTERES_JUSTIFICATIVA = 1000
PRIORIDADES_VALIDAS = {"alta", "media", "baixa", "descartado"}
PASTA_INSTAGRAM = APP_DIR / "instagram"

PASTA_LOGS.mkdir(exist_ok=True)
_handler_log = RotatingFileHandler(
    PASTA_LOGS / "prospeccao.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
)
_handler_log.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.getLogger().addHandler(_handler_log)
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# guarda o estado da busca em andamento (pra não deixar disparar duas ao mesmo tempo
# e pra interface conseguir perguntar "já terminou?"). "etapa" e os contadores dão
# um progresso ao vivo em vez de só uma mensagem estática.
estado_busca = {
    "rodando": False,
    "mensagem": "",
    "etapa": "",  # "scraping" | "verificando_sites" | ""
    "empresas_encontradas": 0,
    "empresas_processadas": 0,
}

# mesmo papel de estado_busca, mas para a análise de um post do Instagram
# (raspar comentários + enriquecer perfis dos autores únicos).
estado_instagram = {
    "rodando": False,
    "mensagem": "",
    "etapa": "",  # "raspando" | "enriquecendo" | ""
    "perfis_encontrados": 0,
    "perfis_processados": 0,
    "post_id": None,
}


def conectar():
    conexao = sqlite3.connect(CAMINHO_BANCO, timeout=10)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA journal_mode=WAL")
    conexao.execute("PRAGMA busy_timeout=10000")
    return conexao


def linha_para_dict(linha):
    return dict(linha)


DIAS_PARA_LEAD_DIFICIL = 5


def calcular_lead_dificil(status, follow_ups_enviados, ultimo_followup_em):
    """Sinaliza um lead como "difícil" quando já levou pelo menos 1 follow-up e
    passaram mais de DIAS_PARA_LEAD_DIFICIL dias sem avançar de estágio - é só uma
    sugestão visual, a decisão de arquivar continua sempre manual."""
    if status not in ("novo", "contatado"):
        return False
    if not follow_ups_enviados or not ultimo_followup_em:
        return False
    try:
        ultimo = datetime.fromisoformat(ultimo_followup_em)
    except ValueError:
        return False
    return (datetime.now() - ultimo).days > DIAS_PARA_LEAD_DIFICIL


def marcar_lead_dificil(lead_dict):
    lead_dict["lead_dificil"] = calcular_lead_dificil(
        lead_dict.get("status"),
        lead_dict.get("follow_ups_enviados"),
        lead_dict.get("ultimo_followup_em"),
    )
    return lead_dict


CHAVES_CONFIG_VALIDAS = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
}

LINKS_OBTER_CHAVE = {
    "gemini": "https://aistudio.google.com/apikey",
    "groq": "https://console.groq.com/keys",
    "nvidia": "https://build.nvidia.com",
}


def obter_config(chave, default=None):
    """Lê uma configuração priorizando a tabela `configuracoes` (editável pela UI)
    e caindo para a variável de ambiente (.env) se não houver nada salvo no banco -
    mantém compatibilidade com quem configura só via .env."""
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


def salvar_config(chave, valor):
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


def mascarar_chave(valor):
    if not valor:
        return None
    if len(valor) <= 4:
        return "•" * len(valor)
    return "•" * 8 + valor[-4:]


@app.route("/api/configuracoes")
def listar_configuracoes():
    resposta = {}
    for chave in CHAVES_CONFIG_VALIDAS:
        valor = obter_config(chave)
        resposta[chave] = {
            "configurada": bool(valor),
            "mascarada": mascarar_chave(valor),
            "link_obter_chave": LINKS_OBTER_CHAVE[chave],
        }
    return jsonify(resposta)


@app.route("/api/configuracoes", methods=["POST"])
def atualizar_configuracao():
    dados = request.json or {}
    chave = dados.get("chave", "")
    valor = str(dados.get("valor", "")).strip()

    if chave not in CHAVES_CONFIG_VALIDAS:
        return jsonify({"erro": f"chave inválida. Use uma de: {', '.join(CHAVES_CONFIG_VALIDAS)}"}), 400
    if not valor:
        return jsonify({"erro": "informe um valor para a chave de API"}), 400

    salvar_config(chave, valor)
    return jsonify({"ok": True, "mascarada": mascarar_chave(valor)})


@app.route("/api/configuracoes/scraper-proxies")
def obter_proxies_scraper():
    proxies = obter_config("scraper_proxies") or ""
    return jsonify({"configurado": bool(proxies), "proxies": proxies})


@app.route("/api/configuracoes/scraper-proxies", methods=["POST"])
def salvar_proxies_scraper():
    """Salva a lista de proxies (opcional) usada pelo google-maps-scraper.exe -
    formato aceito pelo scraper: protocol://user:pass@host:port, separados por
    vírgula. Útil quando o Google bloqueia buscas repetidas vindas do mesmo IP."""
    dados = request.json or {}
    proxies = str(dados.get("proxies", "")).strip()
    salvar_config("scraper_proxies", proxies)
    return jsonify({"ok": True, "configurado": bool(proxies)})


@app.errorhandler(Exception)
def tratar_erro_generico(erro):
    logger.exception("erro não tratado numa rota")
    return jsonify({"erro": "Ocorreu um erro interno. Veja detalhes em logs/prospeccao.log."}), 500


@app.route("/")
def index():
    return render_template("index.html", status_validos=sorted(STATUS_VALIDOS))


LIMITE_PADRAO_LEADS = 30
LIMITE_MAXIMO_LEADS = 200


@app.route("/api/leads")
def listar_leads():
    """Lista os leads, com filtros opcionais via query string: status, nicho, nota_min, busca.
    Paginado via limit/offset (padrão: 30 por página). Resposta: {leads, tem_mais}."""
    status = request.args.get("status", "").strip()
    nicho = request.args.get("nicho", "").strip()
    nota_min_bruta = request.args.get("nota_min", "").strip()
    busca_texto = request.args.get("busca", "").strip()

    try:
        limit = int(request.args.get("limit", LIMITE_PADRAO_LEADS))
    except ValueError:
        return jsonify({"erro": "limit inválido"}), 400
    limit = max(1, min(limit, LIMITE_MAXIMO_LEADS))

    try:
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({"erro": "offset inválido"}), 400
    offset = max(0, offset)

    condicoes = []
    parametros = []

    if status:
        condicoes.append("status = ?")
        parametros.append(status)
    else:
        # por padrão, esconde os leads ignorados da lista principal
        # (só aparecem se o usuário filtrar por status="ignorado" explicitamente)
        condicoes.append("status != 'ignorado'")
    if nicho:
        condicoes.append("nicho = ?")
        parametros.append(nicho)
    if nota_min_bruta:
        try:
            nota_min = float(nota_min_bruta)
        except ValueError:
            return jsonify({"erro": f"nota_min inválida: {nota_min_bruta}"}), 400
        condicoes.append("nota >= ?")
        parametros.append(nota_min)
    if busca_texto:
        condicoes.append("(nome LIKE ? OR endereco LIKE ?)")
        parametros.extend([f"%{busca_texto}%", f"%{busca_texto}%"])

    sql = "SELECT * FROM leads"
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    sql += " ORDER BY visto_em DESC, nota DESC"
    sql += " LIMIT ? OFFSET ?"
    parametros_com_paginacao = [*parametros, limit + 1, offset]

    if not CAMINHO_BANCO.exists():
        return jsonify({"leads": [], "tem_mais": False})

    conexao = conectar()
    try:
        linhas = conexao.execute(sql, parametros_com_paginacao).fetchall()
    finally:
        conexao.close()

    tem_mais = len(linhas) > limit
    linhas = linhas[:limit]

    return jsonify({
        "leads": [marcar_lead_dificil(linha_para_dict(linha)) for linha in linhas],
        "tem_mais": tem_mais,
    })


@app.route("/api/nichos")
def listar_nichos():
    """Lista os valores distintos de nicho (já separado da cidade), pra popular o filtro."""
    if not CAMINHO_BANCO.exists():
        return jsonify([])

    conexao = conectar()
    try:
        linhas = conexao.execute(
            "SELECT DISTINCT nicho FROM leads WHERE nicho IS NOT NULL AND nicho != '' ORDER BY nicho"
        ).fetchall()
    finally:
        conexao.close()

    return jsonify([linha["nicho"] for linha in linhas])


@app.route("/api/metricas")
def metricas():
    """Contagens gerais pro dashboard: total de leads ativos, por status, taxa de conversão."""
    if not CAMINHO_BANCO.exists():
        return jsonify({"total": 0, "por_status": {}, "taxa_conversao": 0})

    conexao = conectar()
    try:
        total = conexao.execute("SELECT COUNT(*) c FROM leads WHERE status != 'ignorado'").fetchone()["c"]
        linhas_por_status = conexao.execute(
            "SELECT status, COUNT(*) c FROM leads WHERE status != 'ignorado' GROUP BY status"
        ).fetchall()
        lembretes_hoje = conexao.execute(
            "SELECT COUNT(*) c FROM leads WHERE status != 'ignorado' AND proximo_followup IS NOT NULL "
            "AND proximo_followup <= ?",
            (date.today().isoformat(),),
        ).fetchone()["c"]
    finally:
        conexao.close()

    por_status = {linha["status"]: linha["c"] for linha in linhas_por_status}
    fechados = por_status.get("fechou", 0)
    taxa_conversao = round(100 * fechados / total, 1) if total else 0

    return jsonify(
        {
            "total": total,
            "por_status": por_status,
            "taxa_conversao": taxa_conversao,
            "lembretes_hoje": lembretes_hoje,
        }
    )


# Ordem "natural" do funil de prospecção - da entrada até o fechamento.
# "recusou" fica de fora do funil (é uma saída, não um estágio de progresso).
ESTAGIOS_FUNIL = ["novo", "contatado", "respondeu", "fechou"]


def _contar_funil_por_tabela(conexao, tabela):
    """Quantos leads (ativos, isto é, não ignorados) já alcançaram cada estágio
    do funil. O funil é uma progressão linear (novo → contatado → respondeu →
    fechou): um lead cujo status atual é "respondeu" conta também em "novo" e
    "contatado", mesmo que tenha pulado direto pra lá sem passar pelo bulk-status
    intermediário. "recusou" não pertence ao funil (é uma saída, não avanço)."""
    status_por_lead = conexao.execute(
        f"SELECT status FROM {tabela} WHERE status != 'ignorado'"
    ).fetchall()

    contagem = {estagio: 0 for estagio in ESTAGIOS_FUNIL}
    for linha in status_por_lead:
        status_atual = linha["status"]
        if status_atual not in ESTAGIOS_FUNIL:
            continue  # "recusou": não avançou em nenhum estágio do funil
        indice_atual = ESTAGIOS_FUNIL.index(status_atual)
        for estagio in ESTAGIOS_FUNIL[: indice_atual + 1]:
            contagem[estagio] += 1

    return contagem


def _contar_por_nicho_tabela(conexao, tabela):
    """Total de leads e taxa de conversão (fechou/total) por nicho (já separado da
    cidade), considerando só leads ativos (não ignorados). Ordenado por total desc."""
    linhas = conexao.execute(
        f"""
        SELECT
            nicho,
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'fechou' THEN 1 ELSE 0 END) AS fechados
        FROM {tabela}
        WHERE status != 'ignorado' AND nicho IS NOT NULL AND nicho != ''
        GROUP BY nicho
        ORDER BY total DESC
        """
    ).fetchall()

    nichos = {}
    for linha in linhas:
        nichos[linha["nicho"]] = {
            "total": linha["total"],
            "fechados": linha["fechados"] or 0,
        }
    return nichos


def _nichos_dict_para_lista(nichos):
    lista = []
    for nome, dados in nichos.items():
        total = dados["total"]
        fechados = dados["fechados"]
        taxa_conversao = round(100 * fechados / total, 1) if total else 0
        lista.append({
            "nicho": nome,
            "total": total,
            "fechados": fechados,
            "taxa_conversao": taxa_conversao,
        })
    lista.sort(key=lambda n: n["total"], reverse=True)
    return lista


@app.route("/api/analytics/funil")
def analytics_funil():
    if not CAMINHO_BANCO.exists():
        return jsonify({"estagios": [{"status": s, "total": 0} for s in ESTAGIOS_FUNIL]})

    conexao = conectar()
    try:
        contagem = _contar_funil_por_tabela(conexao, "leads")
    finally:
        conexao.close()

    return jsonify({
        "estagios": [{"status": s, "total": contagem[s]} for s in ESTAGIOS_FUNIL],
    })


@app.route("/api/analytics/por-nicho")
def analytics_por_nicho():
    if not CAMINHO_BANCO.exists():
        return jsonify({"nichos": []})

    conexao = conectar()
    try:
        nichos = _contar_por_nicho_tabela(conexao, "leads")
    finally:
        conexao.close()

    return jsonify({"nichos": _nichos_dict_para_lista(nichos)})


@app.route("/api/analytics/funil-combinado")
def analytics_funil_combinado():
    conexao = conectar()
    try:
        contagem_maps = (
            _contar_funil_por_tabela(conexao, "leads") if CAMINHO_BANCO.exists() else {e: 0 for e in ESTAGIOS_FUNIL}
        )
        contagem_instagram = _contar_funil_por_tabela(conexao, "instagram_leads")
    finally:
        conexao.close()

    combinado = {
        estagio: contagem_maps[estagio] + contagem_instagram[estagio]
        for estagio in ESTAGIOS_FUNIL
    }
    return jsonify({
        "estagios": [{"status": s, "total": combinado[s]} for s in ESTAGIOS_FUNIL],
    })


@app.route("/api/analytics/por-nicho-combinado")
def analytics_por_nicho_combinado():
    conexao = conectar()
    try:
        nichos_maps = _contar_por_nicho_tabela(conexao, "leads") if CAMINHO_BANCO.exists() else {}
        nichos_instagram = _contar_por_nicho_tabela(conexao, "instagram_leads")
    finally:
        conexao.close()

    combinado = dict(nichos_maps)
    for nome, dados in nichos_instagram.items():
        if nome in combinado:
            combinado[nome] = {
                "total": combinado[nome]["total"] + dados["total"],
                "fechados": combinado[nome]["fechados"] + dados["fechados"],
            }
        else:
            combinado[nome] = dados

    return jsonify({"nichos": _nichos_dict_para_lista(combinado)})


@app.route("/api/leads/<place_id>/status", methods=["POST"])
def atualizar_status(place_id):
    novo_status = (request.json or {}).get("status", "").strip()
    if novo_status not in STATUS_VALIDOS:
        return jsonify({"erro": f"status inválido: {novo_status}"}), 400

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = conectar()
    try:
        lead_atual = conexao.execute("SELECT status FROM leads WHERE place_id = ?", (place_id,)).fetchone()
        if lead_atual is None:
            return jsonify({"erro": "lead não encontrado (pode ter sido excluído)"}), 404

        if novo_status in STATUS_QUE_ENCERRAM_FOLLOWUP:
            conexao.execute(
                "UPDATE leads SET status = ?, proximo_followup = NULL, atualizado_em = ? WHERE place_id = ?",
                (novo_status, agora, place_id),
            )
        else:
            conexao.execute(
                "UPDATE leads SET status = ?, atualizado_em = ? WHERE place_id = ?",
                (novo_status, agora, place_id),
            )
        conexao.execute(
            "INSERT INTO historico_status (place_id, status_anterior, status_novo, alterado_em) VALUES (?, ?, ?, ?)",
            (place_id, lead_atual["status"], novo_status, agora),
        )
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/leads/<place_id>/historico")
def historico_lead(place_id):
    conexao = conectar()
    try:
        linhas = conexao.execute(
            "SELECT status_anterior, status_novo, alterado_em FROM historico_status "
            "WHERE place_id = ? ORDER BY alterado_em DESC",
            (place_id,),
        ).fetchall()
    finally:
        conexao.close()

    return jsonify([linha_para_dict(linha) for linha in linhas])


@app.route("/api/leads/<place_id>/ignorar", methods=["POST"])
def ignorar_lead(place_id):
    """'Exclui' o lead da lista principal sem apagar do banco - ele nunca mais
    volta a aparecer, nem se a mesma busca for rodada de novo no futuro."""
    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE leads SET status = 'ignorado', proximo_followup = NULL, atualizado_em = ? WHERE place_id = ?",
            (datetime.now().isoformat(timespec="seconds"), place_id),
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "lead não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/leads/bulk-status", methods=["POST"])
def atualizar_status_em_lote():
    """Muda o status de vários leads de uma vez, numa única transação."""
    corpo = request.json or {}
    place_ids = corpo.get("place_ids") or []
    novo_status = (corpo.get("status") or "").strip()

    if not place_ids:
        return jsonify({"erro": "informe ao menos um place_id"}), 400
    if novo_status not in STATUS_VALIDOS:
        return jsonify({"erro": f"status inválido: {novo_status}"}), 400

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = conectar()
    try:
        atualizados = 0
        for place_id in place_ids:
            lead_atual = conexao.execute("SELECT status FROM leads WHERE place_id = ?", (place_id,)).fetchone()
            if lead_atual is None:
                continue
            if novo_status in STATUS_QUE_ENCERRAM_FOLLOWUP:
                conexao.execute(
                    "UPDATE leads SET status = ?, proximo_followup = NULL, atualizado_em = ? WHERE place_id = ?",
                    (novo_status, agora, place_id),
                )
            else:
                conexao.execute(
                    "UPDATE leads SET status = ?, atualizado_em = ? WHERE place_id = ?",
                    (novo_status, agora, place_id),
                )
            conexao.execute(
                "INSERT INTO historico_status (place_id, status_anterior, status_novo, alterado_em) VALUES (?, ?, ?, ?)",
                (place_id, lead_atual["status"], novo_status, agora),
            )
            atualizados += 1
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({"ok": True, "atualizados": atualizados})


@app.route("/api/leads/bulk-ignorar", methods=["POST"])
def ignorar_em_lote():
    """Marca vários leads como ignorados de uma vez, numa única transação."""
    place_ids = (request.json or {}).get("place_ids") or []
    if not place_ids:
        return jsonify({"erro": "informe ao menos um place_id"}), 400

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = conectar()
    try:
        placeholders = ",".join("?" for _ in place_ids)
        cursor = conexao.execute(
            f"UPDATE leads SET status = 'ignorado', proximo_followup = NULL, atualizado_em = ? WHERE place_id IN ({placeholders})",
            (agora, *place_ids),
        )
        conexao.commit()
        atualizados = cursor.rowcount
    finally:
        conexao.close()

    return jsonify({"ok": True, "atualizados": atualizados})


@app.route("/api/leads/<place_id>", methods=["DELETE"])
def excluir_lead_definitivamente(place_id):
    """Apaga a linha do banco de vez - sem volta, sem histórico. Só permite excluir
    leads que já estão com status='ignorado' (proteção contra apagar sem querer um
    lead ativo direto pela API; excluir um ativo primeiro exige ignorá-lo)."""
    conexao = conectar()
    try:
        lead = conexao.execute(
            "SELECT status FROM leads WHERE place_id = ?", (place_id,)
        ).fetchone()
        if lead is None:
            return jsonify({"erro": "lead não encontrado"}), 404
        if lead["status"] != "ignorado":
            return jsonify({"erro": "só é possível excluir definitivamente leads já ignorados"}), 400

        conexao.execute("DELETE FROM historico_status WHERE place_id = ?", (place_id,))
        conexao.execute("DELETE FROM leads WHERE place_id = ?", (place_id,))
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/leads/bulk-excluir", methods=["POST"])
def excluir_em_lote_definitivamente():
    """Apaga várias linhas do banco de vez, numa única transação. Mesma proteção
    da versão individual: só apaga leads já 'ignorado', ignora silenciosamente
    qualquer place_id que não esteja nesse estado."""
    place_ids = (request.json or {}).get("place_ids") or []
    if not place_ids:
        return jsonify({"erro": "informe ao menos um place_id"}), 400

    conexao = conectar()
    try:
        placeholders = ",".join("?" for _ in place_ids)
        ids_ignorados = [
            linha["place_id"]
            for linha in conexao.execute(
                f"SELECT place_id FROM leads WHERE place_id IN ({placeholders}) AND status = 'ignorado'",
                place_ids,
            ).fetchall()
        ]

        if ids_ignorados:
            placeholders_validos = ",".join("?" for _ in ids_ignorados)
            conexao.execute(
                f"DELETE FROM historico_status WHERE place_id IN ({placeholders_validos})",
                ids_ignorados,
            )
            conexao.execute(
                f"DELETE FROM leads WHERE place_id IN ({placeholders_validos})",
                ids_ignorados,
            )
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({"ok": True, "excluidos": len(ids_ignorados)})


@app.route("/api/leads/<place_id>/observacoes", methods=["POST"])
def atualizar_observacoes(place_id):
    texto = str((request.json or {}).get("observacoes", ""))
    if len(texto) > MAX_CARACTERES_OBSERVACOES:
        return jsonify({"erro": f"observações muito longas (máximo {MAX_CARACTERES_OBSERVACOES} caracteres)"}), 400

    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE leads SET observacoes = ?, atualizado_em = ? WHERE place_id = ?",
            (texto, datetime.now().isoformat(timespec="seconds"), place_id),
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "lead não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/leads/<place_id>/tags", methods=["POST"])
def atualizar_tags(place_id):
    tags = str((request.json or {}).get("tags", ""))
    if len(tags) > MAX_CARACTERES_TAGS:
        return jsonify({"erro": f"tags muito longas (máximo {MAX_CARACTERES_TAGS} caracteres)"}), 400

    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE leads SET tags = ?, atualizado_em = ? WHERE place_id = ?",
            (tags, datetime.now().isoformat(timespec="seconds"), place_id),
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "lead não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/leads/<place_id>/followup", methods=["POST"])
def atualizar_followup(place_id):
    data = (request.json or {}).get("proximo_followup") or None

    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE leads SET proximo_followup = ?, atualizado_em = ? WHERE place_id = ?",
            (data, datetime.now().isoformat(timespec="seconds"), place_id),
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "lead não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/leads/<place_id>/gerar-mensagem", methods=["POST"])
def gerar_mensagem(place_id):
    corpo = request.json or {}
    forcar_nova = corpo.get("forcar_nova", False)
    tipo = corpo.get("tipo", "contato")
    if tipo not in ("contato", "followup"):
        return jsonify({"erro": "tipo inválido, use 'contato' ou 'followup'"}), 400

    conexao = conectar()
    try:
        lead = conexao.execute("SELECT * FROM leads WHERE place_id = ?", (place_id,)).fetchone()

        if lead is None:
            return jsonify({"erro": "lead não encontrado"}), 404

        if tipo == "contato" and lead["mensagem_gerada"] and not forcar_nova:
            return jsonify({"mensagem": lead["mensagem_gerada"], "cache": True})

        try:
            mensagem, provedor_usado, avisos = gerar_mensagem_com_fallback(
                nome=lead["nome"],
                categoria=lead["categoria"],
                endereco=lead["endereco"],
                nota=lead["nota"],
                tipo=tipo,
                follow_ups_enviados=lead["follow_ups_enviados"] or 0,
            )
        except Exception as erro:
            logger.exception("falha ao gerar mensagem em todos os provedores de IA configurados")
            return jsonify({"erro": str(erro)}), 500

        if tipo == "contato":
            conexao.execute(
                "UPDATE leads SET mensagem_gerada = ?, atualizado_em = ? WHERE place_id = ?",
                (mensagem, datetime.now().isoformat(timespec="seconds"), place_id),
            )
            conexao.commit()
    finally:
        conexao.close()

    return jsonify({"mensagem": mensagem, "cache": False, "provedor": provedor_usado, "avisos": avisos})


def sugerir_proxima_data_followup(follow_ups_enviados):
    """Sugere quantos dias faltam pro próximo follow-up, com cadência crescente
    pra não soar insistente: 1º follow-up +3 dias, 2º +5 dias, 3º em diante +7 dias."""
    if follow_ups_enviados <= 1:
        dias = 3
    elif follow_ups_enviados == 2:
        dias = 5
    else:
        dias = 7
    return (date.today() + timedelta(days=dias)).isoformat()


@app.route("/api/leads/<place_id>/marcar-followup-enviado", methods=["POST"])
def marcar_followup_enviado(place_id):
    agora = datetime.now().isoformat(timespec="seconds")

    conexao = conectar()
    try:
        cursor = conexao.execute(
            "SELECT follow_ups_enviados FROM leads WHERE place_id = ?", (place_id,)
        )
        lead = cursor.fetchone()
        if lead is None:
            return jsonify({"erro": "lead não encontrado"}), 404

        proximo_followup_sugerido = sugerir_proxima_data_followup(
            lead["follow_ups_enviados"] + 1
        )

        conexao.execute(
            """
            UPDATE leads
            SET follow_ups_enviados = follow_ups_enviados + 1,
                ultimo_followup_em = ?,
                proximo_followup = ?,
                atualizado_em = ?
            WHERE place_id = ?
            """,
            (agora, proximo_followup_sugerido, agora, place_id),
        )
        conexao.commit()

        follow_ups_enviados = conexao.execute(
            "SELECT follow_ups_enviados FROM leads WHERE place_id = ?", (place_id,)
        ).fetchone()["follow_ups_enviados"]
    finally:
        conexao.close()

    return jsonify({
        "ok": True,
        "follow_ups_enviados": follow_ups_enviados,
        "ultimo_followup_em": agora,
        "proximo_followup_sugerido": proximo_followup_sugerido,
    })


@app.route("/api/leads/<place_id>/desfazer-followup-enviado", methods=["POST"])
def desfazer_followup_enviado(place_id):
    """Reverte um 'marcar follow-up enviado' feito por engano, restaurando os
    valores anteriores enviados pelo cliente (capturados antes da marcação)."""
    dados = request.json or {}
    follow_ups_enviados_anterior = dados.get("follow_ups_enviados_anterior")
    ultimo_followup_em_anterior = dados.get("ultimo_followup_em_anterior")
    proximo_followup_anterior = dados.get("proximo_followup_anterior")

    if follow_ups_enviados_anterior is None:
        return jsonify({"erro": "follow_ups_enviados_anterior é obrigatório"}), 400

    conexao = conectar()
    try:
        cursor = conexao.execute(
            """
            UPDATE leads
            SET follow_ups_enviados = ?,
                ultimo_followup_em = ?,
                proximo_followup = ?,
                atualizado_em = ?
            WHERE place_id = ?
            """,
            (
                follow_ups_enviados_anterior,
                ultimo_followup_em_anterior,
                proximo_followup_anterior,
                datetime.now().isoformat(timespec="seconds"),
                place_id,
            ),
        )
        if cursor.rowcount == 0:
            return jsonify({"erro": "lead não encontrado"}), 404
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({"ok": True})


def saudacao_por_horario():
    """Calcula a saudação certa a partir da hora real do sistema - a IA não tem
    acesso ao relógio, então isso precisa vir pronto do backend, nunca "adivinhado"
    pelo modelo."""
    hora = datetime.now().hour
    if 5 <= hora < 12:
        return "Bom dia"
    if 12 <= hora < 18:
        return "Boa tarde"
    return "Boa noite"


def montar_prompt_contato(nome, categoria, endereco, nota):
    saudacao = saudacao_por_horario()
    return f"""Você é um copywriter sênior especializado em prospecção B2B fria via WhatsApp, com décadas de experiência em vendas consultivas para pequenos negócios locais no Brasil. Você entende que o dono de uma empresa recebe várias mensagens de spam por semana oferecendo site/marketing, e sabe exatamente o que faz uma mensagem se destacar dessas: especificidade, tom de conversa entre humanos (não de vendedor robótico), e um pedido de ação que seja fácil de responder com "sim" ou "não" em segundos.

Escreva UMA mensagem de primeiro contato (3-5 frases, tom direto e confiante, sem soar arrogante) para a empresa abaixo, oferecendo a criação de um site profissional. A empresa foi encontrada no Google Maps e NÃO possui site cadastrado.

Dados da empresa:
- Nome: {nome}
- Categoria: {categoria or "não informado"}
- Endereço: {endereco or "não informado"}
- Nota no Google: {nota}
- Saudação a usar (calculada pela hora real de agora): {saudacao}

Regras de conteúdo:
- NÃO comece com "Estava navegando/pesquisando no Google e vi..." nem variações disso — é o clichê nº1 de mensagem de spam e qualquer dono de empresa já reconhece isso na hora. Vá direto ao ponto de forma natural.
- Cite o nome da empresa e a categoria dela de forma que pareça que você realmente entende do nicho (ex.: para uma clínica, fale de "agenda de pacientes"; para uma imobiliária, fale de "captação de clientes"; adapte à categoria informada).
- Mencione a nota/reputação como um fato relevante para o argumento (reputação forte + ausência de site = oportunidade perdida), não como um elogio vazio.
- Ofereça a criação do site como solução direta a essa oportunidade perdida, sem enrolação nem múltiplos adjetivos ("profissional", "moderno", "incrível" — use no máximo um).
- Termine com um pedido de ação ESPECÍFICO E FECHADO, nunca uma pergunta aberta tipo "faz sentido conversarmos?" ou "podemos conversar?". Use UMA das duas abordagens, sorteando livremente qual usar a cada geração (não sempre a mesma):
  (a) uma pergunta de sim/não direta sem propor horário (ex.: "Quer que eu te mostre um exemplo rápido?", "Faz sentido eu te mandar uma prévia?", "Posso te enviar uma ideia de como ficaria?");
  (b) uma proposta de horário concreto, mas gerando um horário e dia DIFERENTES a cada vez (não sempre "14h" ou "amanhã de manhã") — varie entre manhã/tarde e diferentes horas cheias ou quebradas ao longo do dia útil.
- Não invente dados que não foram fornecidos (não cite números de clientes, prêmios, ou depoimentos específicos que você não recebeu).

Como tratar o nome (pessoa física vs. empresa) — analise o campo "Nome" acima com atenção:
- Se o nome começar ou for dominado por um nome próprio de pessoa (ex.: "Janete Pugliesi Estética e Depilação à Laser", "Dra. Flávia Andreotti", "Nutricionista Carla Momenti", "Clinica Dra. Ana Souza"), trate a mensagem de forma PESSOAL: dirija-se à pessoa pelo primeiro nome (ex.: "Janete, ..."), use "você" no singular, e fale como se estivesse falando diretamente com a dona/dono do negócio.
- Se o nome for claramente institucional, sem nome de pessoa destacado (ex.: "Consep - Contabilidade e Serviços Empresariais", "Vivarte Odontologia", "Hospital Veterinário 24 horas"), mantenha o tom impessoal/plural de sempre: "vocês", "a equipe da [empresa]", sem inventar ou usar um nome de pessoa que não foi dado.
- Exemplos de abertura para calibrar (não copie literalmente, é só para ilustrar o padrão):
  - Pessoal: "Janete, boa tarde! Vi que a Estética e Depilação à Laser tem nota 5.0, mas sem site você acaba perdendo quem pesquisa por depilação aqui no bairro para a concorrência."
  - Institucional: "Boa tarde! A Vivarte Odontologia tem uma reputação ótima no Google, mas sem site vocês perdem pacientes que buscam clínica odontológica na região para concorrentes com site."
- Use a saudação indicada acima ("{saudacao}") de forma natural na abertura, variando ONDE ela aparece na frase a cada geração (não sempre "Bom dia, [nome]!" fixo no início — às vezes encaixe depois, ex.: "[Nome], bom dia! ...").
- Varie a estrutura da frase de abertura a cada geração — não repita sempre o mesmo molde.
- Retorne APENAS o texto da mensagem, sem aspas, sem explicações extras, sem marcação markdown.
"""


def montar_prompt_followup(nome, categoria, endereco, nota, follow_ups_enviados):
    saudacao = saudacao_por_horario()
    numero_do_followup = max(follow_ups_enviados, 1)
    if numero_do_followup <= 1:
        orientacao_tom = (
            "Este é o PRIMEIRO follow-up (a pessoa não respondeu ao primeiro contato). "
            "Use um tom de reforço gentil e leve, como quem lembra educadamente - sem soar "
            "carente ou insistente. Pode assumir que a mensagem anterior pode ter passado "
            "despercebida no meio de outras conversas."
        )
    else:
        orientacao_tom = (
            f"Este é o follow-up número {numero_do_followup} (já foram enviadas "
            f"{numero_do_followup} mensagens sem resposta). Seja mais direto e conciso que "
            "num primeiro follow-up, mas sem soar impaciente ou passivo-agressivo. Considere "
            "adicionar um elemento novo que não estava nas mensagens anteriores (ex.: um prazo, "
            "uma prova social genérica sobre o valor de ter site, ou perguntar objetivamente se "
            "ainda faz sentido conversar) para não parecer a mesma mensagem repetida."
        )

    return f"""Você é um copywriter sênior especializado em prospecção B2B fria via WhatsApp, com décadas de experiência em vendas consultivas para pequenos negócios locais no Brasil.

Escreva UMA mensagem de FOLLOW-UP (2-4 frases, mais curta que uma mensagem de primeiro contato) para retomar contato com a empresa abaixo, que já recebeu uma mensagem de prospecção sobre criação de site e ainda não respondeu.

Dados da empresa:
- Nome: {nome}
- Categoria: {categoria or "não informado"}
- Endereço: {endereco or "não informado"}
- Nota no Google: {nota}
- Saudação a usar (calculada pela hora real de agora): {saudacao}

Contexto deste follow-up:
{orientacao_tom}

Regras de conteúdo:
- NÃO repita a mesma justificativa/argumento de "nota alta sem site" da mensagem original palavra por palavra - varie a abordagem.
- NÃO comece se desculpando por "incomodar de novo" ou frases que soem inseguras.
- Termine com um pedido de ação ESPECÍFICO E FECHADO (pergunta de sim/não direta OU proposta de horário concreto, sorteando livremente qual usar).
- Não invente dados que não foram fornecidos.
- Use a saudação indicada de forma natural, sem repetir sempre o mesmo molde de abertura.
- Retorne APENAS o texto da mensagem, sem aspas, sem explicações extras, sem marcação markdown.
"""


# Ordem de preferência dos provedores de IA - se o primeiro falhar/estourar cota,
# tenta o próximo automaticamente. Cada usuário pode configurar 1, 2 ou os 3.
ORDEM_PROVEDORES_IA = ["gemini", "groq", "nvidia"]

NOMES_AMIGAVEIS_PROVEDOR = {
    "gemini": "Google Gemini",
    "groq": "Groq",
    "nvidia": "NVIDIA Build",
}

# Evita ficar tentando de novo um provedor que acabou de bater cota - guarda,
# em memória, até quando (time.monotonic()) cada provedor deve ser pulado.
COOLDOWN_COTA_ESTOURADA_SEGUNDOS = 300  # 5 minutos
_provedores_em_cooldown = {}


def _provedor_em_cooldown(provedor):
    expira_em = _provedores_em_cooldown.get(provedor)
    return expira_em is not None and time.monotonic() < expira_em


def _marcar_cooldown_se_cota(provedor, erro):
    if traduzir_erro_ia(erro) == "cota gratuita excedida por agora":
        _provedores_em_cooldown[provedor] = time.monotonic() + COOLDOWN_COTA_ESTOURADA_SEGUNDOS


def gerar_mensagem_com_fallback(nome, categoria, endereco, nota, tipo="contato", follow_ups_enviados=0):
    """Tenta gerar a mensagem em cada provedor configurado, na ordem de preferência.
    Se um provedor falhar (cota excedida, erro, chave ausente), tenta o próximo
    automaticamente. Retorna (mensagem, provedor_usado, avisos_para_o_usuario)."""
    if tipo == "followup":
        prompt = montar_prompt_followup(nome, categoria, endereco, nota, follow_ups_enviados)
    else:
        prompt = montar_prompt_contato(nome, categoria, endereco, nota)

    geradores = {
        "gemini": gemini_gerar_mensagem,
        "groq": groq_gerar_mensagem,
        "nvidia": nvidia_gerar_mensagem,
    }

    avisos = []
    erro_final = None

    for provedor in ORDEM_PROVEDORES_IA:
        if not obter_config(provedor):
            continue  # provedor não configurado, pula silenciosamente

        if _provedor_em_cooldown(provedor):
            logger.info("provedor %s em cooldown (cota excedida recentemente), pulando", provedor)
            avisos.append(f"{NOMES_AMIGAVEIS_PROVEDOR[provedor]} indisponível agora (cota gratuita excedida por agora).")
            continue

        try:
            mensagem = geradores[provedor](prompt)
            logger.info("mensagem gerada com sucesso via %s", provedor)
            return mensagem, provedor, avisos
        except Exception as erro:
            logger.warning("provedor %s falhou ao gerar mensagem: %s", provedor, erro)
            _marcar_cooldown_se_cota(provedor, erro)
            avisos.append(f"{NOMES_AMIGAVEIS_PROVEDOR[provedor]} indisponível agora ({traduzir_erro_ia(erro)}).")
            erro_final = erro
            continue

    if erro_final is None:
        raise RuntimeError(
            "Nenhuma chave de IA configurada. Crie um arquivo .env com GEMINI_API_KEY, "
            "GROQ_API_KEY e/ou NVIDIA_API_KEY (veja .env.example)."
        )
    raise RuntimeError(
        "Todos os provedores de IA configurados falharam agora. "
        f"Último erro: {traduzir_erro_ia(erro_final)}"
    )


def traduzir_erro_ia(erro):
    """Converte erros técnicos de qualquer provedor de IA em mensagens que um usuário leigo entende."""
    texto_erro = str(erro).lower()

    if "api_key" in texto_erro or "api key" in texto_erro or isinstance(erro, RuntimeError):
        return str(erro)
    if "quota" in texto_erro or "resource_exhausted" in texto_erro or "429" in texto_erro or "rate limit" in texto_erro:
        return "cota gratuita excedida por agora"
    if "timeout" in texto_erro or "deadline" in texto_erro:
        return "demorou demais para responder"
    if "unavailable" in texto_erro or "503" in texto_erro:
        return "serviço indisponível no momento"

    return "erro inesperado (veja logs/prospeccao.log)"


def gemini_gerar_mensagem(prompt):
    from google import genai

    chave = obter_config("gemini")
    cliente = genai.Client(api_key=chave)
    resposta = cliente.models.generate_content(model="gemini-flash-latest", contents=prompt)
    return resposta.text.strip()


def groq_gerar_mensagem(prompt):
    from openai import OpenAI

    chave = obter_config("groq")
    cliente = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=chave)
    resposta = cliente.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )
    return resposta.choices[0].message.content.strip()


def nvidia_gerar_mensagem(prompt):
    from openai import OpenAI

    chave = obter_config("nvidia")
    cliente = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=chave)
    resposta = cliente.chat.completions.create(
        model="nvidia/llama-3.3-nemotron-super-49b-v1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
        top_p=0.9,
        max_tokens=512,
    )
    return resposta.choices[0].message.content.strip()


@app.route("/api/exportar")
def exportar_csv():
    """Exporta os leads (respeitando os mesmos filtros da tela) num CSV completo pra download."""
    status = request.args.get("status", "").strip()
    nicho = request.args.get("nicho", "").strip()

    condicoes = []
    parametros = []
    if status:
        condicoes.append("status = ?")
        parametros.append(status)
    else:
        condicoes.append("status != 'ignorado'")
    if nicho:
        condicoes.append("nicho = ?")
        parametros.append(nicho)

    sql = "SELECT * FROM leads"
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    sql += " ORDER BY visto_em DESC, nota DESC"

    conexao = conectar()
    try:
        linhas = conexao.execute(sql, parametros).fetchall()
    finally:
        conexao.close()

    saida = io.StringIO()
    escritor = csv.writer(saida)
    escritor.writerow(
        [
            "nome", "categoria", "endereco", "nota", "num_avaliacoes", "status",
            "tags", "whatsapp_link", "telefone", "observacoes", "nicho", "cidade",
            "query_origem", "proximo_followup", "follow_ups_enviados",
            "ultimo_followup_em", "mensagem_gerada",
        ]
    )
    for lead in linhas:
        escritor.writerow(
            [
                lead["nome"],
                lead["categoria"],
                lead["endereco"],
                lead["nota"],
                lead["num_avaliacoes"],
                lead["status"],
                lead["tags"] or "",
                lead["whatsapp_link"],
                lead["telefone"] or "",
                lead["observacoes"] or "",
                lead["nicho"] or "",
                lead["cidade"] or "",
                lead["query_origem"] or "",
                lead["proximo_followup"] or "",
                lead["follow_ups_enviados"] or 0,
                lead["ultimo_followup_em"] or "",
                lead["mensagem_gerada"] or "",
            ]
        )

    resposta = Response(saida.getvalue(), mimetype="text/csv; charset=utf-8")
    resposta.headers["Content-Disposition"] = "attachment; filename=leads_exportados.csv"
    return resposta


@app.route("/api/buscar", methods=["POST"])
def disparar_busca():
    if estado_busca["rodando"]:
        return jsonify({"erro": "já existe uma busca em andamento"}), 409

    queries_texto = (request.json or {}).get("queries", "").strip()
    if not queries_texto:
        return jsonify({"erro": "informe ao menos um nicho + cidade"}), 400

    linhas_queries = [linha for linha in queries_texto.splitlines() if linha.strip()]
    if len(linhas_queries) > MAX_LINHAS_QUERIES_BUSCA:
        return jsonify({
            "erro": f"no máximo {MAX_LINHAS_QUERIES_BUSCA} linhas por busca (você enviou {len(linhas_queries)})"
        }), 400
    linha_longa_demais = next(
        (linha for linha in linhas_queries if len(linha) > MAX_CARACTERES_POR_LINHA_QUERY), None
    )
    if linha_longa_demais:
        return jsonify({
            "erro": f"uma das linhas passa de {MAX_CARACTERES_POR_LINHA_QUERY} caracteres: "
                    f"\"{linha_longa_demais[:60]}...\""
        }), 400

    caminho_queries = APP_DIR / "queries.txt"
    caminho_queries.write_text(queries_texto + "\n", encoding="utf-8")

    estado_busca["rodando"] = True
    thread = threading.Thread(target=_rodar_busca_em_background, daemon=True)
    thread.start()

    return jsonify({"ok": True})


@app.route("/api/buscar/status")
def status_busca():
    return jsonify(estado_busca)


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


def traduzir_erro_scraper(stderr, returncode):
    """Converte a saída crua do scraper (ou timeout) numa mensagem que o usuário leigo entende."""
    texto = (stderr or "").lower()

    if "could not install driver" in texto or "playwright" in texto:
        return (
            "O scraper não conseguiu iniciar o navegador interno. Confira se o Node.js está "
            "instalado (veja o LEIA-ME.md) e tente novamente."
        )
    if "no such file" in texto or "not found" in texto:
        return "O programa google-maps-scraper.exe não foi encontrado na pasta do projeto."
    if "deadline exceeded" in texto or "timeout" in texto:
        return "A busca no Google Maps demorou demais e foi interrompida. Tente de novo."

    return (
        f"A busca falhou (código {returncode}). Veja os detalhes completos em logs/prospeccao.log."
    )


def _ler_stderr_em_thread(pipe, buffer_lista):
    """Lê stderr continuamente numa thread separada, pra não bloquear o pipe
    (senão o processo trava se encher o buffer de stderr enquanto só lemos stdout)."""
    for linha in iter(pipe.readline, ""):
        buffer_lista.append(linha)
    pipe.close()


def rodar_scraper_com_progresso(comando, cwd, env, timeout_segundos, callback_linha=None):
    """Roda o scraper igual subprocess.run(), mas lê o stdout linha a linha em tempo
    real (em vez de esperar o processo inteiro terminar), chamando callback_linha
    a cada linha - é isso que alimenta o contador de progresso ao vivo."""
    processo = subprocess.Popen(
        comando,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    stderr_linhas = []
    thread_stderr = threading.Thread(
        target=_ler_stderr_em_thread, args=(processo.stderr, stderr_linhas), daemon=True
    )
    thread_stderr.start()

    inicio = time.monotonic()
    try:
        for linha in processo.stdout:
            if time.monotonic() - inicio > timeout_segundos:
                processo.kill()
                processo.wait(timeout=5)
                raise subprocess.TimeoutExpired(comando, timeout_segundos)

            if callback_linha:
                callback_linha(linha)

        tempo_restante = max(1, timeout_segundos - (time.monotonic() - inicio))
        returncode = processo.wait(timeout=tempo_restante)
    except subprocess.TimeoutExpired:
        processo.kill()
        processo.wait(timeout=5)
        raise
    finally:
        processo.stdout.close()
        thread_stderr.join(timeout=5)

    return returncode, "".join(stderr_linhas)


def _processar_linha_de_progresso_scraper(linha_texto):
    linha_texto = linha_texto.strip()
    if not linha_texto:
        return
    try:
        evento = json.loads(linha_texto)
    except json.JSONDecodeError:
        return  # linha não-JSON (algum log solto do binário) - ignora

    mensagem = evento.get("message", "")
    if mensagem == "job finished":
        estado_busca["empresas_processadas"] += 1
        estado_busca["mensagem"] = (
            f"Buscando no Google Maps... {estado_busca['empresas_processadas']} empresa(s) processada(s)"
        )
    elif mensagem.endswith("places found"):
        partes = mensagem.split(" ", 1)
        if partes[0].isdigit():
            estado_busca["empresas_encontradas"] += int(partes[0])


def _callback_progresso_verificacao(indice, total, nome_empresa):
    estado_busca["etapa"] = "verificando_sites"
    estado_busca["mensagem"] = f"Verificando site da empresa {indice} de {total}: {nome_empresa}"
    estado_busca["empresas_processadas"] = indice
    estado_busca["empresas_encontradas"] = total


def _rodar_busca_em_background():
    estado_busca["rodando"] = True
    estado_busca["mensagem"] = "Buscando no Google Maps..."
    estado_busca["etapa"] = "scraping"
    estado_busca["empresas_encontradas"] = 0
    estado_busca["empresas_processadas"] = 0
    logger.info("busca iniciada")

    try:
        fazer_backup_banco()

        data = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        pasta_saidas = APP_DIR / "saidas"
        pasta_saidas.mkdir(exist_ok=True)
        arquivo_bruto = pasta_saidas / f"bruto_{data}.csv"

        ambiente = os.environ.copy()
        ambiente["PLAYWRIGHT_NODEJS_PATH"] = ambiente.get(
            "PLAYWRIGHT_NODEJS_PATH", r"C:\Program Files\nodejs\node.exe"
        )

        comando_scraper = [
            str(APP_DIR / "google-maps-scraper.exe"),
            "-input", str(APP_DIR / "queries.txt"),
            "-results", str(arquivo_bruto),
            "-lang", "pt",
            "-depth", "5",
            "-exit-on-inactivity", "3m",
        ]
        proxies = obter_config("scraper_proxies")
        if proxies:
            comando_scraper += ["-proxies", proxies]

        try:
            returncode, stderr_completo = rodar_scraper_com_progresso(
                comando=comando_scraper,
                cwd=str(APP_DIR),
                env=ambiente,
                timeout_segundos=TIMEOUT_SCRAPER_SEGUNDOS,
                callback_linha=_processar_linha_de_progresso_scraper,
            )
        except subprocess.TimeoutExpired:
            logger.error("scraper excedeu o tempo limite de %ss", TIMEOUT_SCRAPER_SEGUNDOS)
            estado_busca["mensagem"] = (
                "A busca demorou demais e foi cancelada. Tente com menos nichos por vez, "
                "ou confira sua conexão com a internet."
            )
            return
        except FileNotFoundError:
            logger.exception("google-maps-scraper.exe não encontrado")
            estado_busca["mensagem"] = "O programa google-maps-scraper.exe não foi encontrado na pasta do projeto."
            return

        if returncode != 0:
            logger.error("scraper falhou (código %s). stderr: %s", returncode, stderr_completo[-2000:])
            estado_busca["mensagem"] = traduzir_erro_scraper(stderr_completo, returncode)
            return

        estado_busca["mensagem"] = "Filtrando leads e gerando WhatsApp..."
        estado_busca["etapa"] = "verificando_sites"
        estado_busca["empresas_processadas"] = 0
        contagens = processar.processar(arquivo_bruto, callback_progresso=_callback_progresso_verificacao)

        if contagens["total_no_csv"] == 0:
            if estado_busca["empresas_encontradas"] == 0:
                estado_busca["mensagem"] = (
                    "Busca concluída, mas o Google Maps não retornou nenhum resultado - o scraper "
                    "rodou sem erro, só não conseguiu capturar nada. Isso geralmente é bloqueio "
                    "temporário do Google para o seu IP/rede (comum em VPN, rede corporativa ou "
                    "após várias buscas seguidas), não um erro de digitação. Tente novamente mais "
                    "tarde ou numa rede diferente. Veja logs/prospeccao.log para mais detalhes."
                )
            else:
                estado_busca["mensagem"] = (
                    "Busca concluída, mas nenhuma empresa foi encontrada. Confira se o nicho/cidade "
                    "estão escritos corretamente."
                )
        elif contagens["novos"] == 0:
            estado_busca["mensagem"] = (
                f"Busca concluída: nenhum lead novo. {contagens['total_no_csv']} empresa(s) encontrada(s), "
                f"mas todas já eram conhecidas ou tinham site."
            )
        else:
            estado_busca["mensagem"] = f"Busca concluída: {contagens['novos']} lead(s) novo(s) encontrado(s)!"

        logger.info("busca concluída: %s", contagens)

    except Exception:
        logger.exception("erro inesperado durante a busca")
        estado_busca["mensagem"] = "Ocorreu um erro inesperado. Veja detalhes em logs/prospeccao.log."
    finally:
        estado_busca["rodando"] = False
        estado_busca["etapa"] = ""


REGEX_URL_POST_INSTAGRAM = re.compile(r"^https://www\.instagram\.com/(p|reel|tv)/[A-Za-z0-9_-]+/?")


MAX_CARACTERES_NICHO_ALVO = 100


@app.route("/api/instagram/analisar", methods=["POST"])
def analisar_post_instagram():
    if estado_instagram["rodando"]:
        return jsonify({"erro": "já existe uma análise em andamento"}), 409

    corpo = request.json or {}
    post_url = corpo.get("post_url", "").strip()
    nicho_alvo = str(corpo.get("nicho_alvo") or "").strip() or None
    if not post_url or not REGEX_URL_POST_INSTAGRAM.match(post_url):
        return jsonify({"erro": "informe uma URL válida de post do Instagram (ex: https://www.instagram.com/p/XXXXX/)"}), 400
    if nicho_alvo and len(nicho_alvo) > MAX_CARACTERES_NICHO_ALVO:
        return jsonify({"erro": f"nicho-alvo muito longo (máximo {MAX_CARACTERES_NICHO_ALVO} caracteres)"}), 400

    conexao = conectar()
    try:
        cursor = conexao.execute(
            "INSERT INTO instagram_posts (post_url, criado_em, etapa, nicho_alvo) VALUES (?, ?, 'pendente', ?)",
            (post_url, datetime.now().isoformat(timespec="seconds"), nicho_alvo),
        )
        conexao.commit()
        post_id = cursor.lastrowid
    finally:
        conexao.close()

    estado_instagram["rodando"] = True
    thread = threading.Thread(
        target=_rodar_analise_instagram_em_background,
        args=(post_id, post_url, nicho_alvo),
        daemon=True,
    )
    thread.start()

    return jsonify({"ok": True, "post_id": post_id})


@app.route("/api/instagram/status")
def status_instagram():
    return jsonify(estado_instagram)


@app.route("/api/instagram/posts")
def listar_posts_instagram():
    ver_arquivados = request.args.get("arquivados", "").strip().lower() == "true"
    condicao = "arquivado_em IS NOT NULL" if ver_arquivados else "arquivado_em IS NULL"

    conexao = conectar()
    try:
        posts = [linha_para_dict(l) for l in conexao.execute(
            f"SELECT * FROM instagram_posts WHERE {condicao} ORDER BY id DESC"
        ).fetchall()]
        for post in posts:
            contagem = conexao.execute(
                """
                SELECT
                    SUM(CASE WHEN prioridade = 'alta' THEN 1 ELSE 0 END) AS alta,
                    SUM(CASE WHEN prioridade = 'media' THEN 1 ELSE 0 END) AS media,
                    SUM(CASE WHEN prioridade = 'baixa' THEN 1 ELSE 0 END) AS baixa,
                    SUM(CASE WHEN prioridade = 'descartado' THEN 1 ELSE 0 END) AS descartado,
                    SUM(CASE WHEN prioridade IS NULL AND status != 'ignorado' THEN 1 ELSE 0 END) AS pendente,
                    SUM(CASE WHEN status = 'ignorado' THEN 1 ELSE 0 END) AS ignorado,
                    COUNT(*) AS total
                FROM instagram_leads WHERE post_id = ?
                """,
                (post["id"],),
            ).fetchone()
            post["contagem_leads"] = linha_para_dict(contagem)
    finally:
        conexao.close()

    return jsonify({"posts": posts})


@app.route("/api/instagram/posts/<int:post_id>/arquivar", methods=["POST"])
def arquivar_post_instagram(post_id):
    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE instagram_posts SET arquivado_em = ? WHERE id = ?",
            (datetime.now().isoformat(timespec="seconds"), post_id),
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "post não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/instagram/posts/<int:post_id>/desarquivar", methods=["POST"])
def desarquivar_post_instagram(post_id):
    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE instagram_posts SET arquivado_em = NULL WHERE id = ?", (post_id,)
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "post não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/instagram/posts/<int:post_id>", methods=["DELETE"])
def excluir_post_instagram_definitivamente(post_id):
    """Apaga o post e todos os leads/histórico relacionados de vez. Só permite
    excluir posts já arquivados (mesma proteção usada em leads individuais,
    contra apagar sem querer um post ativo)."""
    conexao = conectar()
    try:
        post = conexao.execute(
            "SELECT arquivado_em FROM instagram_posts WHERE id = ?", (post_id,)
        ).fetchone()
        if post is None:
            return jsonify({"erro": "post não encontrado"}), 404
        if post["arquivado_em"] is None:
            return jsonify({"erro": "só é possível excluir definitivamente posts já arquivados"}), 400

        ids_leads = [
            linha["id"]
            for linha in conexao.execute(
                "SELECT id FROM instagram_leads WHERE post_id = ?", (post_id,)
            ).fetchall()
        ]
        if ids_leads:
            placeholders = ",".join("?" * len(ids_leads))
            conexao.execute(
                f"DELETE FROM historico_status_instagram WHERE lead_id IN ({placeholders})",
                ids_leads,
            )
        conexao.execute("DELETE FROM instagram_leads WHERE post_id = ?", (post_id,))
        conexao.execute("DELETE FROM instagram_posts WHERE id = ?", (post_id,))
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({"ok": True})


def _montar_filtro_leads_instagram(post_id):
    """Monta a condição WHERE e os parâmetros pros endpoints de listar/exportar
    leads do Instagram, aplicando os mesmos filtros: status (por padrão, esconde
    'ignorado'), e busca textual em username/bio/comentários."""
    status = request.args.get("status", "").strip()
    nicho = request.args.get("nicho", "").strip()
    busca_texto = request.args.get("busca", "").strip()

    condicoes = ["post_id = ?"]
    parametros = [post_id]

    if status:
        condicoes.append("status = ?")
        parametros.append(status)
    else:
        # por padrão, esconde os leads ignorados da lista principal
        # (só aparecem se o usuário filtrar por status="ignorado" explicitamente)
        condicoes.append("status != 'ignorado'")

    if nicho:
        condicoes.append("nicho = ?")
        parametros.append(nicho)

    if busca_texto:
        condicoes.append("(username LIKE ? OR biography LIKE ? OR comentarios LIKE ?)")
        parametros.extend([f"%{busca_texto}%", f"%{busca_texto}%", f"%{busca_texto}%"])

    return " AND ".join(condicoes), parametros


@app.route("/api/instagram/posts/<int:post_id>/leads")
def listar_leads_instagram(post_id):
    condicao, parametros = _montar_filtro_leads_instagram(post_id)

    conexao = conectar()
    try:
        leads = [linha_para_dict(l) for l in conexao.execute(
            f"SELECT * FROM instagram_leads WHERE {condicao} ORDER BY id", parametros
        ).fetchall()]
    finally:
        conexao.close()

    for lead in leads:
        lead["comentarios"] = json.loads(lead["comentarios"]) if lead["comentarios"] else []
        marcar_lead_dificil(lead)

    return jsonify({"leads": leads})


@app.route("/api/instagram/posts/<int:post_id>/exportar")
def exportar_csv_instagram(post_id):
    """Exporta os leads de um post do Instagram (respeitando os mesmos filtros
    da tela) num CSV completo pra download."""
    condicao, parametros = _montar_filtro_leads_instagram(post_id)

    conexao = conectar()
    try:
        linhas = conexao.execute(
            f"SELECT * FROM instagram_leads WHERE {condicao} ORDER BY id", parametros
        ).fetchall()
    finally:
        conexao.close()

    saida = io.StringIO()
    escritor = csv.writer(saida)
    escritor.writerow(
        [
            "username", "full_name", "biography", "seguidores", "is_private",
            "is_business_account", "status", "prioridade", "nicho", "tags",
            "sugestao_dm", "justificativa", "observacoes", "proximo_followup",
            "follow_ups_enviados", "ultimo_followup_em", "comentarios",
        ]
    )
    for lead in linhas:
        comentarios = json.loads(lead["comentarios"]) if lead["comentarios"] else []
        escritor.writerow(
            [
                lead["username"],
                lead["full_name"],
                lead["biography"],
                lead["seguidores"],
                bool(lead["is_private"]),
                bool(lead["is_business_account"]),
                lead["status"],
                lead["prioridade"],
                lead["nicho"] or "",
                lead["tags"] or "",
                lead["sugestao_dm"] or "",
                lead["justificativa"] or "",
                lead["observacoes"] or "",
                lead["proximo_followup"] or "",
                lead["follow_ups_enviados"] or 0,
                lead["ultimo_followup_em"] or "",
                "; ".join(comentarios),
            ]
        )

    resposta = Response(saida.getvalue(), mimetype="text/csv; charset=utf-8")
    resposta.headers["Content-Disposition"] = "attachment; filename=leads_instagram_exportados.csv"
    return resposta


MAX_CARACTERES_NICHO_INSTAGRAM = 100


@app.route("/api/instagram/leads/<int:lead_id>/analise", methods=["POST"])
def gravar_analise_lead_instagram(lead_id):
    dados = request.json or {}
    prioridade = dados.get("prioridade")
    justificativa = str(dados.get("justificativa", ""))
    sugestao_dm = str(dados.get("sugestao_dm", ""))
    nicho = str(dados.get("nicho", ""))

    if prioridade not in PRIORIDADES_VALIDAS:
        return jsonify({"erro": f"prioridade inválida (use: {', '.join(sorted(PRIORIDADES_VALIDAS))})"}), 400
    if len(justificativa) > MAX_CARACTERES_JUSTIFICATIVA:
        return jsonify({"erro": f"justificativa muito longa (máximo {MAX_CARACTERES_JUSTIFICATIVA} caracteres)"}), 400
    if len(sugestao_dm) > MAX_CARACTERES_SUGESTAO_DM:
        return jsonify({"erro": f"sugestão de DM muito longa (máximo {MAX_CARACTERES_SUGESTAO_DM} caracteres)"}), 400
    if len(nicho) > MAX_CARACTERES_NICHO_INSTAGRAM:
        return jsonify({"erro": f"nicho muito longo (máximo {MAX_CARACTERES_NICHO_INSTAGRAM} caracteres)"}), 400

    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE instagram_leads SET prioridade = ?, justificativa = ?, sugestao_dm = ?, nicho = ?, atualizado_em = ? WHERE id = ?",
            (prioridade, justificativa, sugestao_dm, nicho, datetime.now().isoformat(timespec="seconds"), lead_id),
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "lead não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/instagram/leads/bulk-analise", methods=["POST"])
def gravar_analise_lead_instagram_em_lote():
    itens = (request.json or {}).get("leads", [])
    if not isinstance(itens, list) or not itens:
        return jsonify({"erro": "envie {\"leads\": [{id, prioridade, justificativa, sugestao_dm, nicho}, ...]}"}), 400

    for item in itens:
        if item.get("prioridade") not in PRIORIDADES_VALIDAS:
            return jsonify({"erro": f"prioridade inválida em um dos leads (id={item.get('id')})"}), 400
        if len(str(item.get("justificativa", ""))) > MAX_CARACTERES_JUSTIFICATIVA:
            return jsonify({"erro": f"justificativa muito longa em um dos leads (id={item.get('id')})"}), 400
        if len(str(item.get("sugestao_dm", ""))) > MAX_CARACTERES_SUGESTAO_DM:
            return jsonify({"erro": f"sugestão de DM muito longa em um dos leads (id={item.get('id')})"}), 400
        if len(str(item.get("nicho", ""))) > MAX_CARACTERES_NICHO_INSTAGRAM:
            return jsonify({"erro": f"nicho muito longo em um dos leads (id={item.get('id')})"}), 400

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = conectar()
    try:
        atualizados = 0
        for item in itens:
            cursor = conexao.execute(
                "UPDATE instagram_leads SET prioridade = ?, justificativa = ?, sugestao_dm = ?, nicho = ?, atualizado_em = ? WHERE id = ?",
                (
                    item["prioridade"],
                    str(item.get("justificativa", "")),
                    str(item.get("sugestao_dm", "")),
                    str(item.get("nicho", "")),
                    agora,
                    item["id"],
                ),
            )
            atualizados += cursor.rowcount
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({"ok": True, "atualizados": atualizados})


@app.route("/api/instagram/leads/<int:lead_id>/status", methods=["POST"])
def atualizar_status_lead_instagram(lead_id):
    novo_status = (request.json or {}).get("status", "").strip()
    if novo_status not in STATUS_VALIDOS:
        return jsonify({"erro": f"status inválido: {novo_status}"}), 400

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = conectar()
    try:
        lead_atual = conexao.execute(
            "SELECT status FROM instagram_leads WHERE id = ?", (lead_id,)
        ).fetchone()
        if lead_atual is None:
            return jsonify({"erro": "lead não encontrado"}), 404

        if novo_status in STATUS_QUE_ENCERRAM_FOLLOWUP:
            conexao.execute(
                "UPDATE instagram_leads SET status = ?, proximo_followup = NULL, atualizado_em = ? WHERE id = ?",
                (novo_status, agora, lead_id),
            )
        else:
            conexao.execute(
                "UPDATE instagram_leads SET status = ?, atualizado_em = ? WHERE id = ?",
                (novo_status, agora, lead_id),
            )
        conexao.execute(
            "INSERT INTO historico_status_instagram (lead_id, status_anterior, status_novo, alterado_em) VALUES (?, ?, ?, ?)",
            (lead_id, lead_atual["status"], novo_status, agora),
        )
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/instagram/leads/<int:lead_id>/historico")
def historico_lead_instagram(lead_id):
    conexao = conectar()
    try:
        linhas = conexao.execute(
            "SELECT status_anterior, status_novo, alterado_em FROM historico_status_instagram "
            "WHERE lead_id = ? ORDER BY alterado_em DESC",
            (lead_id,),
        ).fetchall()
    finally:
        conexao.close()

    return jsonify([linha_para_dict(linha) for linha in linhas])


@app.route("/api/instagram/leads/<int:lead_id>/ignorar", methods=["POST"])
def ignorar_lead_instagram(lead_id):
    """'Exclui' o lead da lista principal sem apagar do banco - reversível."""
    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE instagram_leads SET status = 'ignorado', proximo_followup = NULL, atualizado_em = ? WHERE id = ?",
            (datetime.now().isoformat(timespec="seconds"), lead_id),
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "lead não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/instagram/leads/bulk-status", methods=["POST"])
def atualizar_status_em_lote_instagram():
    corpo = request.json or {}
    lead_ids = corpo.get("lead_ids") or []
    novo_status = (corpo.get("status") or "").strip()

    if not lead_ids:
        return jsonify({"erro": "informe ao menos um lead_id"}), 400
    if novo_status not in STATUS_VALIDOS:
        return jsonify({"erro": f"status inválido: {novo_status}"}), 400

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = conectar()
    try:
        atualizados = 0
        for lead_id in lead_ids:
            lead_atual = conexao.execute(
                "SELECT status FROM instagram_leads WHERE id = ?", (lead_id,)
            ).fetchone()
            if lead_atual is None:
                continue
            if novo_status in STATUS_QUE_ENCERRAM_FOLLOWUP:
                conexao.execute(
                    "UPDATE instagram_leads SET status = ?, proximo_followup = NULL, atualizado_em = ? WHERE id = ?",
                    (novo_status, agora, lead_id),
                )
            else:
                conexao.execute(
                    "UPDATE instagram_leads SET status = ?, atualizado_em = ? WHERE id = ?",
                    (novo_status, agora, lead_id),
                )
            conexao.execute(
                "INSERT INTO historico_status_instagram (lead_id, status_anterior, status_novo, alterado_em) VALUES (?, ?, ?, ?)",
                (lead_id, lead_atual["status"], novo_status, agora),
            )
            atualizados += 1
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({"ok": True, "atualizados": atualizados})


@app.route("/api/instagram/leads/bulk-ignorar", methods=["POST"])
def ignorar_em_lote_instagram():
    lead_ids = (request.json or {}).get("lead_ids") or []
    if not lead_ids:
        return jsonify({"erro": "informe ao menos um lead_id"}), 400

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = conectar()
    try:
        placeholders = ",".join("?" for _ in lead_ids)
        cursor = conexao.execute(
            f"UPDATE instagram_leads SET status = 'ignorado', proximo_followup = NULL, atualizado_em = ? WHERE id IN ({placeholders})",
            (agora, *lead_ids),
        )
        conexao.commit()
        atualizados = cursor.rowcount
    finally:
        conexao.close()

    return jsonify({"ok": True, "atualizados": atualizados})


@app.route("/api/instagram/leads/<int:lead_id>", methods=["DELETE"])
def excluir_lead_instagram_definitivamente(lead_id):
    """Apaga a linha do banco de vez. Só permite excluir leads já 'ignorado'
    (mesma proteção do CRM de Maps, contra apagar sem querer um lead ativo)."""
    conexao = conectar()
    try:
        lead = conexao.execute(
            "SELECT status FROM instagram_leads WHERE id = ?", (lead_id,)
        ).fetchone()
        if lead is None:
            return jsonify({"erro": "lead não encontrado"}), 404
        if lead["status"] != "ignorado":
            return jsonify({"erro": "só é possível excluir definitivamente leads já ignorados"}), 400

        conexao.execute("DELETE FROM historico_status_instagram WHERE lead_id = ?", (lead_id,))
        conexao.execute("DELETE FROM instagram_leads WHERE id = ?", (lead_id,))
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/instagram/leads/bulk-excluir", methods=["POST"])
def excluir_em_lote_definitivamente_instagram():
    lead_ids = (request.json or {}).get("lead_ids") or []
    if not lead_ids:
        return jsonify({"erro": "informe ao menos um lead_id"}), 400

    conexao = conectar()
    try:
        placeholders = ",".join("?" for _ in lead_ids)
        ids_ignorados = [
            linha["id"]
            for linha in conexao.execute(
                f"SELECT id FROM instagram_leads WHERE id IN ({placeholders}) AND status = 'ignorado'",
                lead_ids,
            ).fetchall()
        ]
        if ids_ignorados:
            placeholders_ignorados = ",".join("?" for _ in ids_ignorados)
            conexao.execute(
                f"DELETE FROM historico_status_instagram WHERE lead_id IN ({placeholders_ignorados})",
                ids_ignorados,
            )
            conexao.execute(
                f"DELETE FROM instagram_leads WHERE id IN ({placeholders_ignorados})",
                ids_ignorados,
            )
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({"ok": True, "excluidos": len(ids_ignorados)})


MAX_CARACTERES_OBSERVACOES_INSTAGRAM = 5000
MAX_CARACTERES_TAGS_INSTAGRAM = 500


@app.route("/api/instagram/leads/<int:lead_id>/observacoes", methods=["POST"])
def atualizar_observacoes_instagram(lead_id):
    texto = str((request.json or {}).get("observacoes", ""))
    if len(texto) > MAX_CARACTERES_OBSERVACOES_INSTAGRAM:
        return jsonify({"erro": f"observações muito longas (máximo {MAX_CARACTERES_OBSERVACOES_INSTAGRAM} caracteres)"}), 400

    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE instagram_leads SET observacoes = ?, atualizado_em = ? WHERE id = ?",
            (texto, datetime.now().isoformat(timespec="seconds"), lead_id),
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "lead não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/instagram/leads/<int:lead_id>/tags", methods=["POST"])
def atualizar_tags_instagram(lead_id):
    tags = str((request.json or {}).get("tags", ""))
    if len(tags) > MAX_CARACTERES_TAGS_INSTAGRAM:
        return jsonify({"erro": f"tags muito longas (máximo {MAX_CARACTERES_TAGS_INSTAGRAM} caracteres)"}), 400

    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE instagram_leads SET tags = ?, atualizado_em = ? WHERE id = ?",
            (tags, datetime.now().isoformat(timespec="seconds"), lead_id),
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "lead não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/instagram/leads/<int:lead_id>/followup", methods=["POST"])
def atualizar_followup_instagram(lead_id):
    data = (request.json or {}).get("proximo_followup") or None

    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE instagram_leads SET proximo_followup = ?, atualizado_em = ? WHERE id = ?",
            (data, datetime.now().isoformat(timespec="seconds"), lead_id),
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "lead não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/instagram/leads/<int:lead_id>/marcar-followup-enviado", methods=["POST"])
def marcar_followup_enviado_instagram(lead_id):
    agora = datetime.now().isoformat(timespec="seconds")

    conexao = conectar()
    try:
        cursor = conexao.execute(
            "SELECT follow_ups_enviados FROM instagram_leads WHERE id = ?", (lead_id,)
        )
        lead = cursor.fetchone()
        if lead is None:
            return jsonify({"erro": "lead não encontrado"}), 404

        proximo_followup_sugerido = sugerir_proxima_data_followup(
            lead["follow_ups_enviados"] + 1
        )

        conexao.execute(
            """
            UPDATE instagram_leads
            SET follow_ups_enviados = follow_ups_enviados + 1,
                ultimo_followup_em = ?,
                proximo_followup = ?,
                atualizado_em = ?
            WHERE id = ?
            """,
            (agora, proximo_followup_sugerido, agora, lead_id),
        )
        conexao.commit()

        follow_ups_enviados = conexao.execute(
            "SELECT follow_ups_enviados FROM instagram_leads WHERE id = ?", (lead_id,)
        ).fetchone()["follow_ups_enviados"]
    finally:
        conexao.close()

    return jsonify({
        "ok": True,
        "follow_ups_enviados": follow_ups_enviados,
        "ultimo_followup_em": agora,
        "proximo_followup_sugerido": proximo_followup_sugerido,
    })


@app.route("/api/instagram/leads/<int:lead_id>/desfazer-followup-enviado", methods=["POST"])
def desfazer_followup_enviado_instagram(lead_id):
    """Reverte um 'marcar follow-up enviado' feito por engano (versão Instagram)."""
    dados = request.json or {}
    follow_ups_enviados_anterior = dados.get("follow_ups_enviados_anterior")
    ultimo_followup_em_anterior = dados.get("ultimo_followup_em_anterior")
    proximo_followup_anterior = dados.get("proximo_followup_anterior")

    if follow_ups_enviados_anterior is None:
        return jsonify({"erro": "follow_ups_enviados_anterior é obrigatório"}), 400

    conexao = conectar()
    try:
        cursor = conexao.execute(
            """
            UPDATE instagram_leads
            SET follow_ups_enviados = ?,
                ultimo_followup_em = ?,
                proximo_followup = ?,
                atualizado_em = ?
            WHERE id = ?
            """,
            (
                follow_ups_enviados_anterior,
                ultimo_followup_em_anterior,
                proximo_followup_anterior,
                datetime.now().isoformat(timespec="seconds"),
                lead_id,
            ),
        )
        if cursor.rowcount == 0:
            return jsonify({"erro": "lead não encontrado"}), 404
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/instagram/leads/<int:lead_id>/sugestao-dm", methods=["POST"])
def salvar_sugestao_dm_instagram(lead_id):
    texto = str((request.json or {}).get("sugestao_dm", ""))
    if len(texto) > MAX_CARACTERES_SUGESTAO_DM:
        return jsonify({"erro": f"sugestão de DM muito longa (máximo {MAX_CARACTERES_SUGESTAO_DM} caracteres)"}), 400

    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE instagram_leads SET sugestao_dm = ?, atualizado_em = ? WHERE id = ?",
            (texto, datetime.now().isoformat(timespec="seconds"), lead_id),
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "lead não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


def montar_prompt_contato_instagram(username, full_name, biography, nicho, justificativa):
    saudacao = saudacao_por_horario()
    return f"""Você é um copywriter sênior especializado em prospecção B2B fria via DM do Instagram, com décadas de experiência em vendas consultivas para pequenos negócios locais no Brasil.

Escreva UMA mensagem de primeiro contato (2-4 frases, tom leve e informal - é DM do Instagram, não WhatsApp/e-mail formal) para a pessoa/perfil abaixo, oferecendo a criação de um site profissional.

Dados do perfil:
- Username: @{username}
- Nome: {full_name or "não informado"}
- Bio: {biography or "não informada"}
- Nicho identificado: {nicho or "não identificado"}
- Justificativa da análise (por que esse perfil foi priorizado): {justificativa or "não informada"}
- Saudação a usar (calculada pela hora real de agora): {saudacao}

Regras de conteúdo:
- Tom de DM real entre duas pessoas, nunca de "mensagem automática de empresa" - sem "prezado(a)", sem formalidade excessiva.
- Cite algo específico da bio ou do nicho identificado pra mostrar que não é uma mensagem copiada e colada pra qualquer perfil.
- NÃO comece com "Oi, tudo bem? Vi seu perfil..." nem variações clichês disso.
- Ofereça a criação do site como solução direta, sem múltiplos adjetivos.
- Termine com um pedido de ação específico e fechado (pergunta de sim/não direta ou proposta de horário).
- Não invente dados que não foram fornecidos.
- Retorne APENAS o texto da mensagem, sem aspas, sem explicações extras, sem marcação markdown.
"""


def montar_prompt_followup_instagram(username, full_name, biography, nicho, follow_ups_enviados):
    saudacao = saudacao_por_horario()
    numero_do_followup = max(follow_ups_enviados, 1)
    if numero_do_followup <= 1:
        orientacao_tom = (
            "Este é o PRIMEIRO follow-up (a pessoa não respondeu à primeira DM). Tom de "
            "reforço leve e casual, como quem manda mais uma mensagem sem grande peso - "
            "DMs se perdem fácil no Instagram, então pode assumir isso com naturalidade."
        )
    else:
        orientacao_tom = (
            f"Este é o follow-up número {numero_do_followup} (já foram enviadas "
            f"{numero_do_followup} DMs sem resposta). Seja mais direto e breve, sem soar "
            "insistente. Considere perguntar objetivamente se ainda faz sentido ou oferecer algo novo."
        )

    return f"""Você é um copywriter sênior especializado em prospecção B2B fria via DM do Instagram.

Escreva UMA mensagem de FOLLOW-UP (1-3 frases, curta e casual) pra retomar contato com o perfil abaixo, que já recebeu uma DM sobre criação de site e não respondeu.

Dados do perfil:
- Username: @{username}
- Nome: {full_name or "não informado"}
- Bio: {biography or "não informada"}
- Nicho identificado: {nicho or "não identificado"}
- Saudação a usar (calculada pela hora real de agora): {saudacao}

Contexto deste follow-up:
{orientacao_tom}

Regras de conteúdo:
- NÃO repita a mesma justificativa da DM original palavra por palavra.
- NÃO se desculpe por "incomodar de novo".
- Termine com um pedido de ação específico e fechado.
- Retorne APENAS o texto da mensagem, sem aspas, sem explicações extras, sem marcação markdown.
"""


def gerar_mensagem_instagram_com_fallback(username, full_name, biography, nicho, justificativa, tipo, follow_ups_enviados):
    if tipo == "followup":
        prompt = montar_prompt_followup_instagram(username, full_name, biography, nicho, follow_ups_enviados)
    else:
        prompt = montar_prompt_contato_instagram(username, full_name, biography, nicho, justificativa)

    geradores = {
        "gemini": gemini_gerar_mensagem,
        "groq": groq_gerar_mensagem,
        "nvidia": nvidia_gerar_mensagem,
    }

    avisos = []
    erro_final = None

    for provedor in ORDEM_PROVEDORES_IA:
        if not obter_config(provedor):
            continue

        if _provedor_em_cooldown(provedor):
            avisos.append(f"{NOMES_AMIGAVEIS_PROVEDOR[provedor]} indisponível agora (cota gratuita excedida por agora).")
            continue

        try:
            mensagem = geradores[provedor](prompt)
            return mensagem, provedor, avisos
        except Exception as erro:
            logger.warning("provedor %s falhou ao gerar mensagem (Instagram): %s", provedor, erro)
            _marcar_cooldown_se_cota(provedor, erro)
            avisos.append(f"{NOMES_AMIGAVEIS_PROVEDOR[provedor]} indisponível agora ({traduzir_erro_ia(erro)}).")
            erro_final = erro
            continue

    if erro_final is None:
        raise RuntimeError(
            "Nenhuma chave de IA configurada. Configure em /configuracoes ou no arquivo .env."
        )
    raise RuntimeError(
        f"Todos os provedores de IA configurados falharam agora. Último erro: {traduzir_erro_ia(erro_final)}"
    )


@app.route("/api/instagram/leads/<int:lead_id>/gerar-mensagem", methods=["POST"])
def gerar_mensagem_instagram(lead_id):
    corpo = request.json or {}
    tipo = corpo.get("tipo", "contato")
    forcar_nova = corpo.get("forcar_nova", False)
    if tipo not in ("contato", "followup"):
        return jsonify({"erro": "tipo inválido, use 'contato' ou 'followup'"}), 400

    conexao = conectar()
    try:
        lead = conexao.execute(
            "SELECT * FROM instagram_leads WHERE id = ?", (lead_id,)
        ).fetchone()

        if lead is None:
            return jsonify({"erro": "lead não encontrado"}), 404

        if tipo == "contato" and lead["sugestao_dm"] and not forcar_nova:
            return jsonify({"mensagem": lead["sugestao_dm"], "cache": True})

        try:
            mensagem, provedor_usado, avisos = gerar_mensagem_instagram_com_fallback(
                username=lead["username"],
                full_name=lead["full_name"],
                biography=lead["biography"],
                nicho=lead["nicho"],
                justificativa=lead["justificativa"],
                tipo=tipo,
                follow_ups_enviados=lead["follow_ups_enviados"] or 0,
            )
        except Exception as erro:
            logger.exception("falha ao gerar mensagem (Instagram) em todos os provedores de IA configurados")
            return jsonify({"erro": str(erro)}), 500

        if tipo == "contato":
            conexao.execute(
                "UPDATE instagram_leads SET sugestao_dm = ?, atualizado_em = ? WHERE id = ?",
                (mensagem, datetime.now().isoformat(timespec="seconds"), lead_id),
            )
            conexao.commit()
    finally:
        conexao.close()

    return jsonify({"mensagem": mensagem, "cache": False, "provedor": provedor_usado, "avisos": avisos})


@app.route("/api/instagram/nichos")
def listar_nichos_instagram():
    """Lista os valores distintos de nicho já preenchidos em instagram_leads, pra popular o filtro."""
    conexao = conectar()
    try:
        linhas = conexao.execute(
            "SELECT DISTINCT nicho FROM instagram_leads WHERE nicho IS NOT NULL AND nicho != '' ORDER BY nicho"
        ).fetchall()
    finally:
        conexao.close()

    return jsonify([linha["nicho"] for linha in linhas])


@app.route("/api/instagram/metricas")
def metricas_instagram():
    """Contagens gerais dos leads do Instagram: total ativos, por status, taxa de conversão."""
    conexao = conectar()
    try:
        total = conexao.execute(
            "SELECT COUNT(*) c FROM instagram_leads WHERE status != 'ignorado'"
        ).fetchone()["c"]
        linhas_por_status = conexao.execute(
            "SELECT status, COUNT(*) c FROM instagram_leads WHERE status != 'ignorado' GROUP BY status"
        ).fetchall()
        lembretes_hoje = conexao.execute(
            "SELECT COUNT(*) c FROM instagram_leads WHERE status != 'ignorado' AND proximo_followup IS NOT NULL "
            "AND proximo_followup <= ?",
            (date.today().isoformat(),),
        ).fetchone()["c"]
    finally:
        conexao.close()

    por_status = {linha["status"]: linha["c"] for linha in linhas_por_status}
    fechados = por_status.get("fechou", 0)
    taxa_conversao = round(100 * fechados / total, 1) if total else 0

    return jsonify({
        "total": total,
        "por_status": por_status,
        "taxa_conversao": taxa_conversao,
        "lembretes_hoje": lembretes_hoje,
    })


@app.route("/api/metricas-combinadas")
def metricas_combinadas():
    """Soma as métricas dos dois canais (Maps + Instagram) - usado no dashboard
    unificado. Reaproveita as mesmas queries de /api/metricas e /api/instagram/metricas,
    só que somando os totais em vez de devolver dois blocos separados."""
    conexao = conectar()
    try:
        total_maps = 0
        por_status_maps = {}
        if CAMINHO_BANCO.exists():
            total_maps = conexao.execute(
                "SELECT COUNT(*) c FROM leads WHERE status != 'ignorado'"
            ).fetchone()["c"]
            por_status_maps = {
                linha["status"]: linha["c"]
                for linha in conexao.execute(
                    "SELECT status, COUNT(*) c FROM leads WHERE status != 'ignorado' GROUP BY status"
                ).fetchall()
            }
        hoje_local = date.today().isoformat()
        lembretes_maps = conexao.execute(
            "SELECT COUNT(*) c FROM leads WHERE status != 'ignorado' AND proximo_followup IS NOT NULL "
            "AND proximo_followup <= ?",
            (hoje_local,),
        ).fetchone()["c"] if CAMINHO_BANCO.exists() else 0

        total_instagram = conexao.execute(
            "SELECT COUNT(*) c FROM instagram_leads WHERE status != 'ignorado'"
        ).fetchone()["c"]
        por_status_instagram = {
            linha["status"]: linha["c"]
            for linha in conexao.execute(
                "SELECT status, COUNT(*) c FROM instagram_leads WHERE status != 'ignorado' GROUP BY status"
            ).fetchall()
        }
        lembretes_instagram = conexao.execute(
            "SELECT COUNT(*) c FROM instagram_leads WHERE status != 'ignorado' AND proximo_followup IS NOT NULL "
            "AND proximo_followup <= ?",
            (hoje_local,),
        ).fetchone()["c"]
    finally:
        conexao.close()

    total = total_maps + total_instagram
    por_status_combinado = dict(por_status_maps)
    for status, contagem in por_status_instagram.items():
        por_status_combinado[status] = por_status_combinado.get(status, 0) + contagem
    fechados = por_status_combinado.get("fechou", 0)
    taxa_conversao = round(100 * fechados / total, 1) if total else 0

    return jsonify({
        "total": total,
        "por_status": por_status_combinado,
        "taxa_conversao": taxa_conversao,
        "lembretes_hoje": lembretes_maps + lembretes_instagram,
        "maps": {"total": total_maps, "lembretes_hoje": lembretes_maps},
        "instagram": {"total": total_instagram, "lembretes_hoje": lembretes_instagram},
    })


CHAVE_CONFIG_META_SEMANAL = "meta_semanal_contatos"


def inicio_semana_atual_iso():
    """Segunda-feira desta semana, à meia-noite, em formato ISO - início do
    período que a meta semanal de contatos considera."""
    hoje = date.today()
    segunda = hoje - timedelta(days=hoje.weekday())
    return datetime.combine(segunda, datetime.min.time()).isoformat(timespec="seconds")


@app.route("/api/meta-semanal")
def obter_meta_semanal():
    """Retorna a meta semanal configurada (leads contatados) e o progresso desde
    a última segunda-feira, contando transições para 'contatado' nos dois canais."""
    meta_str = obter_config(CHAVE_CONFIG_META_SEMANAL)
    meta = int(meta_str) if meta_str and meta_str.isdigit() else 0

    inicio_semana = inicio_semana_atual_iso()
    conexao = conectar()
    try:
        contatos_maps = conexao.execute(
            "SELECT COUNT(*) c FROM historico_status WHERE status_novo = 'contatado' AND alterado_em >= ?",
            (inicio_semana,),
        ).fetchone()["c"]
        contatos_instagram = conexao.execute(
            "SELECT COUNT(*) c FROM historico_status_instagram WHERE status_novo = 'contatado' AND alterado_em >= ?",
            (inicio_semana,),
        ).fetchone()["c"]
    finally:
        conexao.close()

    progresso = contatos_maps + contatos_instagram
    return jsonify({
        "meta": meta,
        "progresso": progresso,
        "faltam": max(meta - progresso, 0) if meta else 0,
        "porcentagem": round(100 * progresso / meta, 1) if meta else 0,
        "inicio_semana": inicio_semana[:10],
    })


@app.route("/api/meta-semanal", methods=["POST"])
def salvar_meta_semanal():
    dados = request.json or {}
    meta = dados.get("meta")

    if not isinstance(meta, int) or meta < 0:
        return jsonify({"erro": "meta deve ser um número inteiro maior ou igual a 0"}), 400

    salvar_config(CHAVE_CONFIG_META_SEMANAL, str(meta))
    return jsonify({"ok": True, "meta": meta})


@app.route("/api/follow-ups-hoje")
def follow_ups_hoje():
    """Lista os leads com follow-up vencido ou para hoje, dos dois canais juntos -
    ordenados pela data do follow-up (mais atrasado primeiro)."""
    conexao = conectar()
    try:
        hoje_local = date.today().isoformat()
        leads_maps = []
        if CAMINHO_BANCO.exists():
            leads_maps = [
                linha_para_dict(l) for l in conexao.execute(
                    "SELECT place_id, nome AS titulo, proximo_followup, status, 'maps' AS canal "
                    "FROM leads WHERE status != 'ignorado' AND proximo_followup IS NOT NULL "
                    "AND proximo_followup <= ? ORDER BY proximo_followup",
                    (hoje_local,),
                ).fetchall()
            ]
        leads_instagram = [
            linha_para_dict(l) for l in conexao.execute(
                "SELECT id AS place_id, username AS titulo, proximo_followup, status, 'instagram' AS canal "
                "FROM instagram_leads WHERE status != 'ignorado' AND proximo_followup IS NOT NULL "
                "AND proximo_followup <= ? ORDER BY proximo_followup",
                (hoje_local,),
            ).fetchall()
        ]
    finally:
        conexao.close()

    combinados = sorted(leads_maps + leads_instagram, key=lambda l: l["proximo_followup"])
    return jsonify({"leads": combinados})


@app.route("/api/instagram/analytics/funil")
def analytics_funil_instagram():
    """Mesma lógica cumulativa de /api/analytics/funil, mas sobre instagram_leads."""
    conexao = conectar()
    try:
        contagem = _contar_funil_por_tabela(conexao, "instagram_leads")
    finally:
        conexao.close()

    return jsonify({
        "estagios": [{"status": s, "total": contagem[s]} for s in ESTAGIOS_FUNIL],
    })


@app.route("/api/instagram/analytics/por-nicho")
def analytics_por_nicho_instagram():
    """Mesma lógica de /api/analytics/por-nicho, mas sobre instagram_leads."""
    conexao = conectar()
    try:
        nichos = _contar_por_nicho_tabela(conexao, "instagram_leads")
    finally:
        conexao.close()

    return jsonify({"nichos": _nichos_dict_para_lista(nichos)})


def _callback_progresso_enriquecimento_instagram(indice, total, username):
    estado_instagram["etapa"] = "enriquecendo"
    estado_instagram["mensagem"] = f"Consultando perfil {indice} de {total}: @{username}"
    estado_instagram["perfis_processados"] = indice
    estado_instagram["perfis_encontrados"] = total


PRIORIDADES_VALIDAS_CLASSIFICACAO = {"alta", "media", "baixa", "descartado"}

DOMINIOS_LINK_NA_BIO = (
    "wa.me",
    "api.whatsapp.com",
    "whatsapp.com",
    "linktr.ee",
    "linkr.bio",
    "beacons.ai",
    "allmylinks.com",
    "instagram.com",
    "bio.link",
    "linkbio.co",
    "solo.to",
    "campsite.bio",
    "carrd.co",
)


def perfil_tem_site_proprio(perfil):
    """Heurística determinística (sem custo de IA): considera 'site próprio' quando
    o link da bio (external_url) aponta para um domínio que não é um agregador de
    link conhecido (WhatsApp, Linktree e afins) - sinal de que o negócio já tem site."""
    url = (perfil.get("external_url") or "").strip().lower()
    if not url:
        return False
    return not any(dominio in url for dominio in DOMINIOS_LINK_NA_BIO)


def montar_prompt_classificacao_instagram(perfil, nicho_alvo):
    comentarios = perfil.get("comentarios", [])
    trecho_comentarios = "\n".join(f'- "{c}"' for c in comentarios[:5]) or "(nenhum comentário capturado)"
    contexto_nicho = (
        f'O usuário está procurando especificamente por leads do nicho "{nicho_alvo}". '
        "Dê prioridade mais alta a perfis que pareçam pertencer a esse nicho, e priorize mais "
        "baixo (ou 'baixa') perfis que claramente não pertençam a ele, mesmo que sejam bons leads "
        "de outro tipo."
        if nicho_alvo
        else "O usuário não informou um nicho-alvo específico - avalie de forma geral, priorizando "
        "donos de pequenos negócios locais sem site próprio."
    )

    return f"""Você é um analista de qualificação de leads para uma agência que vende criação de sites para pequenos negócios locais no Brasil, avaliando um perfil do Instagram que comentou numa publicação.

{contexto_nicho}

Dados do perfil:
- Username: @{perfil.get("username")}
- Nome: {perfil.get("full_name") or "não informado"}
- Bio: {perfil.get("biography") or "não informada"}
- Seguidores: {perfil.get("seguidores") or 0}
- Conta comercial (business account): {"sim" if perfil.get("is_business_account") else "não"}
- Comentários feitos no post analisado:
{trecho_comentarios}

Tarefa: avalie se esse perfil é um bom lead (dono de pequeno negócio local, sem site próprio aparente, que se beneficiaria de ter um site) e retorne um JSON com EXATAMENTE estas chaves:
- "prioridade": uma destas strings: "alta", "media", "baixa", "descartado" (use "descartado" só se não houver indício nenhum de ser um negócio/profissional real, ex: perfil pessoal sem relação com negócios).
- "nicho": uma string curta com o nicho/profissão identificado (ex: "advogado", "esteticista", "dentista"), ou string vazia "" se não for possível identificar.
- "justificativa": 1-2 frases explicando o motivo da prioridade escolhida.
- "sugestao_dm": uma sugestão curta e casual de mensagem de DM para esse perfil (2-4 frases, tom de Instagram - só preencha se prioridade for "alta" ou "media"; caso contrário retorne string vazia "").

Retorne APENAS o JSON, sem markdown, sem explicações fora do JSON.
"""


def classificar_lead_instagram_com_fallback(perfil, nicho_alvo):
    """Classifica um perfil do Instagram (prioridade/nicho/justificativa/sugestão de DM)
    usando o mesmo fallback de provedores de IA já usado para gerar mensagens, mas pedindo
    resposta em JSON estruturado. Levanta exceção se todos os provedores falharem -
    quem chama deve tratar por perfil, sem abortar o lote inteiro."""
    prompt = montar_prompt_classificacao_instagram(perfil, nicho_alvo)

    geradores = {
        "gemini": gemini_gerar_mensagem,
        "groq": groq_gerar_mensagem,
        "nvidia": nvidia_gerar_mensagem,
    }

    erro_final = None
    for provedor in ORDEM_PROVEDORES_IA:
        if not obter_config(provedor):
            continue
        if _provedor_em_cooldown(provedor):
            continue
        try:
            resposta_bruta = geradores[provedor](prompt)
            resposta_limpa = resposta_bruta.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            dados = json.loads(resposta_limpa)

            prioridade = str(dados.get("prioridade", "")).strip().lower()
            if prioridade not in PRIORIDADES_VALIDAS_CLASSIFICACAO:
                prioridade = "baixa"

            return {
                "prioridade": prioridade,
                "nicho": str(dados.get("nicho", "")).strip()[:MAX_CARACTERES_NICHO_INSTAGRAM] or None,
                "justificativa": str(dados.get("justificativa", "")).strip()[:MAX_CARACTERES_JUSTIFICATIVA],
                "sugestao_dm": str(dados.get("sugestao_dm", "")).strip()[:MAX_CARACTERES_SUGESTAO_DM],
            }
        except Exception as erro:
            logger.warning("provedor %s falhou ao classificar perfil @%s: %s", provedor, perfil.get("username"), erro)
            _marcar_cooldown_se_cota(provedor, erro)
            erro_final = erro
            continue

    raise RuntimeError(f"nenhum provedor de IA conseguiu classificar o perfil (último erro: {erro_final})")


def _rodar_analise_instagram_em_background(post_id, post_url, nicho_alvo=None):
    estado_instagram["rodando"] = True
    estado_instagram["mensagem"] = "Extraindo comentários do post..."
    estado_instagram["etapa"] = "raspando"
    estado_instagram["perfis_encontrados"] = 0
    estado_instagram["perfis_processados"] = 0
    estado_instagram["post_id"] = post_id
    logger.info("análise do Instagram iniciada para post_id=%s", post_id)

    def marcar_erro(mensagem):
        estado_instagram["mensagem"] = mensagem
        conexao = conectar()
        try:
            conexao.execute(
                "UPDATE instagram_posts SET etapa = 'erro', erro_mensagem = ? WHERE id = ?",
                (mensagem, post_id),
            )
            conexao.commit()
        finally:
            conexao.close()

    try:
        import raspar_comentarios
        import enriquecer_perfis

        conexao = conectar()
        try:
            conexao.execute("UPDATE instagram_posts SET etapa = 'raspando' WHERE id = ?", (post_id,))
            conexao.commit()
        finally:
            conexao.close()

        try:
            caminho_comentarios = raspar_comentarios.raspar_comentarios(post_url)
        except RuntimeError as erro:
            marcar_erro(str(erro))
            return
        except Exception as erro:
            marcar_erro(f"Erro ao acessar o post (pode ser privado, removido, ou rate limit): {erro}")
            return

        dados_comentarios = json.loads(Path(caminho_comentarios).read_text(encoding="utf-8"))

        estado_instagram["mensagem"] = "Enriquecendo perfis dos autores dos comentários..."
        estado_instagram["etapa"] = "enriquecendo"

        conexao = conectar()
        try:
            conexao.execute(
                "UPDATE instagram_posts SET etapa = 'enriquecendo', total_comentarios = ? WHERE id = ?",
                (dados_comentarios["total_comentarios"], post_id),
            )
            conexao.commit()
        finally:
            conexao.close()

        try:
            caminho_enriquecido = enriquecer_perfis.enriquecer_perfis(
                Path(caminho_comentarios), callback_progresso=_callback_progresso_enriquecimento_instagram
            )
        except RuntimeError as erro:
            marcar_erro(str(erro))
            return

        dados_enriquecidos = json.loads(Path(caminho_enriquecido).read_text(encoding="utf-8"))

        estado_instagram["mensagem"] = "Classificando perfis com IA..."
        estado_instagram["etapa"] = "classificando"
        total_perfis = len(dados_enriquecidos["perfis"])
        classificacoes = {}
        for indice, perfil in enumerate(dados_enriquecidos["perfis"], start=1):
            estado_instagram["mensagem"] = f"Classificando perfil {indice} de {total_perfis}: @{perfil.get('username')}"
            if perfil.get("is_private"):
                continue  # mesma regra do prompt manual: descarta privados sem gastar chamada de IA
            if perfil.get("erro"):
                continue  # coleta do perfil falhou (rate limit, sessão expirada etc.) - não há dado real pra classificar
            if perfil_tem_site_proprio(perfil):
                continue  # já tem site próprio na bio - não é o perfil de lead que buscamos
            try:
                classificacoes[perfil["username"]] = classificar_lead_instagram_com_fallback(perfil, nicho_alvo)
            except Exception as erro:
                logger.warning("classificação por IA falhou para @%s, seguindo sem prioridade: %s", perfil.get("username"), erro)

        conexao = conectar()
        try:
            for perfil in dados_enriquecidos["perfis"]:
                classificacao = classificacoes.get(perfil["username"], {})
                tem_site_proprio = perfil_tem_site_proprio(perfil)
                observacoes = (
                    f"Perfil não avaliado - falha na coleta: {perfil['erro']}"
                    if perfil.get("erro")
                    else "Perfil ignorado automaticamente - já tem site próprio na bio."
                    if tem_site_proprio
                    else None
                )
                status_inicial = (
                    "ignorado"
                    if perfil.get("is_private") or tem_site_proprio
                    else "novo"
                )
                conexao.execute(
                    """
                    INSERT INTO instagram_leads
                        (post_id, username, full_name, is_private, biography, seguidores, is_business_account, comentarios,
                         prioridade, nicho, justificativa, sugestao_dm, observacoes, status, atualizado_em)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        post_id,
                        perfil["username"],
                        perfil.get("full_name"),
                        int(bool(perfil.get("is_private"))) if "is_private" in perfil else None,
                        perfil.get("biography"),
                        perfil.get("seguidores"),
                        int(bool(perfil.get("is_business_account"))) if "is_business_account" in perfil else None,
                        json.dumps(perfil.get("comentarios", []), ensure_ascii=False),
                        classificacao.get("prioridade"),
                        classificacao.get("nicho"),
                        classificacao.get("justificativa"),
                        classificacao.get("sugestao_dm"),
                        observacoes,
                        status_inicial,
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
            conexao.execute(
                "UPDATE instagram_posts SET etapa = 'concluido', total_perfis = ? WHERE id = ?",
                (len(dados_enriquecidos["perfis"]), post_id),
            )
            conexao.commit()
        finally:
            conexao.close()

        estado_instagram["mensagem"] = f"Análise concluída: {len(dados_enriquecidos['perfis'])} perfil(is) encontrado(s)."
        logger.info("análise do Instagram concluída para post_id=%s", post_id)

    except Exception:
        logger.exception("erro inesperado na análise do Instagram")
        marcar_erro("Ocorreu um erro inesperado. Veja detalhes em logs/prospeccao.log.")
    finally:
        estado_instagram["rodando"] = False
        estado_instagram["etapa"] = ""


MAX_CARACTERES_TITULO_TEMPLATE = 100
MAX_CARACTERES_TEXTO_TEMPLATE = 3000


@app.route("/api/templates")
def listar_templates():
    """Lista templates de mensagem, com filtro opcional por nicho via query string."""
    nicho = request.args.get("nicho", "").strip()

    sql = "SELECT * FROM templates_mensagem"
    parametros = []
    if nicho:
        sql += " WHERE nicho = ?"
        parametros.append(nicho)
    sql += " ORDER BY vezes_usado DESC, atualizado_em DESC"

    conexao = conectar()
    try:
        templates = [linha_para_dict(l) for l in conexao.execute(sql, parametros).fetchall()]
    finally:
        conexao.close()

    return jsonify({"templates": templates})


@app.route("/api/templates", methods=["POST"])
def criar_template():
    dados = request.json or {}
    titulo = str(dados.get("titulo", "")).strip()
    texto = str(dados.get("texto", "")).strip()
    nicho = str(dados.get("nicho", "")).strip() or None

    if not titulo:
        return jsonify({"erro": "informe um título para o template"}), 400
    if len(titulo) > MAX_CARACTERES_TITULO_TEMPLATE:
        return jsonify({"erro": f"título muito longo (máximo {MAX_CARACTERES_TITULO_TEMPLATE} caracteres)"}), 400
    if not texto:
        return jsonify({"erro": "informe o texto do template"}), 400
    if len(texto) > MAX_CARACTERES_TEXTO_TEMPLATE:
        return jsonify({"erro": f"texto muito longo (máximo {MAX_CARACTERES_TEXTO_TEMPLATE} caracteres)"}), 400

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = conectar()
    try:
        cursor = conexao.execute(
            "INSERT INTO templates_mensagem (titulo, texto, nicho, vezes_usado, criado_em, atualizado_em) "
            "VALUES (?, ?, ?, 0, ?, ?)",
            (titulo, texto, nicho, agora, agora),
        )
        conexao.commit()
        template_id = cursor.lastrowid
    finally:
        conexao.close()

    return jsonify({"ok": True, "id": template_id})


@app.route("/api/templates/<int:template_id>", methods=["PUT"])
def atualizar_template(template_id):
    dados = request.json or {}
    titulo = str(dados.get("titulo", "")).strip()
    texto = str(dados.get("texto", "")).strip()
    nicho = str(dados.get("nicho", "")).strip() or None

    if not titulo:
        return jsonify({"erro": "informe um título para o template"}), 400
    if len(titulo) > MAX_CARACTERES_TITULO_TEMPLATE:
        return jsonify({"erro": f"título muito longo (máximo {MAX_CARACTERES_TITULO_TEMPLATE} caracteres)"}), 400
    if not texto:
        return jsonify({"erro": "informe o texto do template"}), 400
    if len(texto) > MAX_CARACTERES_TEXTO_TEMPLATE:
        return jsonify({"erro": f"texto muito longo (máximo {MAX_CARACTERES_TEXTO_TEMPLATE} caracteres)"}), 400

    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE templates_mensagem SET titulo = ?, texto = ?, nicho = ?, atualizado_em = ? WHERE id = ?",
            (titulo, texto, nicho, datetime.now().isoformat(timespec="seconds"), template_id),
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "template não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/templates/<int:template_id>", methods=["DELETE"])
def excluir_template(template_id):
    conexao = conectar()
    try:
        cursor = conexao.execute("DELETE FROM templates_mensagem WHERE id = ?", (template_id,))
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "template não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@app.route("/api/templates/<int:template_id>/usar", methods=["POST"])
def registrar_uso_template(template_id):
    """Incrementa o contador de uso do template (chamado quando o usuário usa
    o template como base pra uma mensagem de abordagem)."""
    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE templates_mensagem SET vezes_usado = vezes_usado + 1, atualizado_em = ? WHERE id = ?",
            (datetime.now().isoformat(timespec="seconds"), template_id),
        )
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "template não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


def preparar_banco_no_startup():
    """Garante que o schema esteja atualizado assim que o app sobe, mesmo que o
    usuário ainda não tenha rodado nenhuma busca nesta instalação."""
    conexao = sqlite3.connect(CAMINHO_BANCO, timeout=10)
    try:
        processar.preparar_banco(conexao)
    finally:
        conexao.close()


preparar_banco_no_startup()


if __name__ == "__main__":
    modo_dev = os.environ.get("PROSPECCAO_DEBUG", "false").lower() == "true"
    app.run(debug=modo_dev, port=5000)
