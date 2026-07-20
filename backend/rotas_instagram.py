"""Rotas do canal Instagram: disparo da análise de post, posts (arquivar/excluir),
leads (funil, tags, observações, follow-up, DM) e exportação."""

import csv
import io
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from flask import Blueprint, Response, jsonify, request

import db
import ia
import jobs
import paths
from constantes import (
    MAX_CARACTERES_JUSTIFICATIVA,
    MAX_CARACTERES_NICHO_ALVO,
    MAX_CARACTERES_NICHO_INSTAGRAM,
    MAX_CARACTERES_OBSERVACOES_INSTAGRAM,
    MAX_CARACTERES_SUGESTAO_DM,
    MAX_CARACTERES_TAGS_INSTAGRAM,
    MAX_IDS_BULK,
    PRIORIDADES_VALIDAS,
    STATUS_QUE_ENCERRAM_FOLLOWUP,
    STATUS_VALIDOS,
)
from rotas_leads import marcar_lead_dificil, sugerir_proxima_data_followup
from validacao import validar_ids_bulk

logger = logging.getLogger(__name__)

bp = Blueprint("instagram", __name__)

REGEX_URL_POST_INSTAGRAM = re.compile(r"^https://www\.instagram\.com/(p|reel|tv)/[A-Za-z0-9_-]+/?")


@bp.route("/api/instagram/analisar", methods=["POST"])
def analisar_post_instagram():
    corpo = request.json or {}
    post_url = corpo.get("post_url", "").strip()
    nicho_alvo = str(corpo.get("nicho_alvo") or "").strip() or None
    if not post_url or not REGEX_URL_POST_INSTAGRAM.match(post_url):
        return jsonify({"erro": "informe uma URL válida de post do Instagram (ex: https://www.instagram.com/p/XXXXX/)"}), 400
    if nicho_alvo and len(nicho_alvo) > MAX_CARACTERES_NICHO_ALVO:
        return jsonify({"erro": f"nicho-alvo muito longo (máximo {MAX_CARACTERES_NICHO_ALVO} caracteres)"}), 400

    if not jobs.tentar_reservar_analise_instagram():
        return jsonify({"erro": "já existe uma análise em andamento"}), 409

    try:
        conexao = db.conectar()
        try:
            cursor = conexao.execute(
                "INSERT INTO instagram_posts (post_url, criado_em, etapa, nicho_alvo) VALUES (?, ?, 'pendente', ?)",
                (post_url, datetime.now().isoformat(timespec="seconds"), nicho_alvo),
            )
            conexao.commit()
            post_id = cursor.lastrowid
        finally:
            conexao.close()

        jobs.iniciar_thread_analise_instagram(post_id, post_url, nicho_alvo)
    except Exception:
        jobs.liberar_analise_instagram()  # senão a flag ficaria presa em True pra sempre
        raise

    return jsonify({"ok": True, "post_id": post_id})


@bp.route("/api/instagram/status")
def status_instagram():
    return jsonify(jobs.estado_instagram)


def _pode_retomar(post):
    """Uma análise pode ser retomada quando terminou em erro e o JSON de
    comentários daquela rodada ainda existe em disco (aí não precisa raspar
    o post de novo - o enriquecimento continua do parcial salvo)."""
    return bool(
        post["etapa"] == "erro"
        and post["arquivo_comentarios"]
        and Path(post["arquivo_comentarios"]).exists()
    )


@bp.route("/api/instagram/posts/<int:post_id>/retomar", methods=["POST"])
def retomar_analise_instagram(post_id):
    """Retoma uma análise que parou no meio (checkpoint, rate limit, queda do
    backend): reaproveita os comentários já raspados e os perfis já enriquecidos,
    consultando só o que faltou."""
    conexao = db.conectar()
    try:
        post = conexao.execute(
            "SELECT * FROM instagram_posts WHERE id = ?", (post_id,)
        ).fetchone()
    finally:
        conexao.close()

    if post is None:
        return jsonify({"erro": "post não encontrado"}), 404
    if post["etapa"] == "concluido":
        return jsonify({"erro": "esta análise já foi concluída"}), 400
    if not _pode_retomar(post):
        return jsonify({
            "erro": "não dá para retomar esta análise (os comentários raspados não foram "
                    "encontrados) - inicie uma nova análise com a URL do post"
        }), 400

    if not jobs.tentar_reservar_analise_instagram():
        return jsonify({"erro": "já existe uma análise em andamento"}), 409

    try:
        conexao = db.conectar()
        try:
            conexao.execute(
                "UPDATE instagram_posts SET etapa = 'pendente', erro_mensagem = NULL WHERE id = ?",
                (post_id,),
            )
            conexao.commit()
        finally:
            conexao.close()

        jobs.iniciar_thread_analise_instagram(
            post_id, post["post_url"], post["nicho_alvo"], post["arquivo_comentarios"]
        )
    except Exception:
        jobs.liberar_analise_instagram()  # senão a flag ficaria presa em True pra sempre
        raise

    return jsonify({"ok": True, "post_id": post_id})


@bp.route("/api/instagram/posts")
def listar_posts_instagram():
    ver_arquivados = request.args.get("arquivados", "").strip().lower() == "true"
    condicao = "arquivado_em IS NOT NULL" if ver_arquivados else "arquivado_em IS NULL"

    conexao = db.conectar()
    try:
        posts = [db.linha_para_dict(l) for l in conexao.execute(
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
            post["contagem_leads"] = db.linha_para_dict(contagem)
            post["pode_retomar"] = _pode_retomar(post)
    finally:
        conexao.close()

    return jsonify({"posts": posts})


@bp.route("/api/instagram/posts/<int:post_id>/arquivar", methods=["POST"])
def arquivar_post_instagram(post_id):
    conexao = db.conectar()
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


@bp.route("/api/instagram/posts/<int:post_id>/desarquivar", methods=["POST"])
def desarquivar_post_instagram(post_id):
    conexao = db.conectar()
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


@bp.route("/api/instagram/posts/<int:post_id>", methods=["DELETE"])
def excluir_post_instagram_definitivamente(post_id):
    """Apaga o post e todos os leads/histórico relacionados de vez. Só permite
    excluir posts já arquivados (mesma proteção usada em leads individuais,
    contra apagar sem querer um post ativo)."""
    conexao = db.conectar()
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


def _comentarios_do_lead(lead):
    """Comentários do lead como lista, tolerante a JSON corrompido - uma linha
    com dado inválido não pode derrubar a listagem/exportação inteira (500)."""
    try:
        return json.loads(lead["comentarios"]) if lead["comentarios"] else []
    except (TypeError, json.JSONDecodeError):
        logger.warning("comentarios com JSON inválido no lead id=%s, tratando como vazio", lead["id"])
        return []


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


@bp.route("/api/instagram/posts/<int:post_id>/leads")
def listar_leads_instagram(post_id):
    condicao, parametros = _montar_filtro_leads_instagram(post_id)

    conexao = db.conectar()
    try:
        leads = [db.linha_para_dict(l) for l in conexao.execute(
            f"SELECT * FROM instagram_leads WHERE {condicao} ORDER BY id", parametros
        ).fetchall()]
    finally:
        conexao.close()

    for lead in leads:
        lead["comentarios"] = _comentarios_do_lead(lead)
        marcar_lead_dificil(lead)

    return jsonify({"leads": leads})


@bp.route("/api/instagram/posts/<int:post_id>/exportar")
def exportar_csv_instagram(post_id):
    """Exporta os leads de um post do Instagram (respeitando os mesmos filtros
    da tela) num CSV completo pra download."""
    condicao, parametros = _montar_filtro_leads_instagram(post_id)

    conexao = db.conectar()
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
        comentarios = _comentarios_do_lead(lead)
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


@bp.route("/api/instagram/leads/<int:lead_id>/analise", methods=["POST"])
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

    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/bulk-analise", methods=["POST"])
def gravar_analise_lead_instagram_em_lote():
    itens = (request.json or {}).get("leads", [])
    if not isinstance(itens, list) or not itens:
        return jsonify({"erro": "envie {\"leads\": [{id, prioridade, justificativa, sugestao_dm, nicho}, ...]}"}), 400
    if len(itens) > MAX_IDS_BULK:
        return jsonify({"erro": f"no máximo {MAX_IDS_BULK} leads por vez (você enviou {len(itens)})"}), 400

    for item in itens:
        if not isinstance(item, dict) or "id" not in item:
            return jsonify({"erro": "cada lead precisa ter um 'id'"}), 400
        if item.get("prioridade") not in PRIORIDADES_VALIDAS:
            return jsonify({"erro": f"prioridade inválida em um dos leads (id={item.get('id')})"}), 400
        if len(str(item.get("justificativa", ""))) > MAX_CARACTERES_JUSTIFICATIVA:
            return jsonify({"erro": f"justificativa muito longa em um dos leads (id={item.get('id')})"}), 400
        if len(str(item.get("sugestao_dm", ""))) > MAX_CARACTERES_SUGESTAO_DM:
            return jsonify({"erro": f"sugestão de DM muito longa em um dos leads (id={item.get('id')})"}), 400
        if len(str(item.get("nicho", ""))) > MAX_CARACTERES_NICHO_INSTAGRAM:
            return jsonify({"erro": f"nicho muito longo em um dos leads (id={item.get('id')})"}), 400

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/<int:lead_id>/status", methods=["POST"])
def atualizar_status_lead_instagram(lead_id):
    novo_status = (request.json or {}).get("status", "").strip()
    if novo_status not in STATUS_VALIDOS:
        return jsonify({"erro": f"status inválido: {novo_status}"}), 400

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/<int:lead_id>/historico")
def historico_lead_instagram(lead_id):
    conexao = db.conectar()
    try:
        linhas = conexao.execute(
            "SELECT status_anterior, status_novo, alterado_em FROM historico_status_instagram "
            "WHERE lead_id = ? ORDER BY alterado_em DESC",
            (lead_id,),
        ).fetchall()
    finally:
        conexao.close()

    return jsonify([db.linha_para_dict(linha) for linha in linhas])


@bp.route("/api/instagram/leads/<int:lead_id>/ignorar", methods=["POST"])
def ignorar_lead_instagram(lead_id):
    """'Exclui' o lead da lista principal sem apagar do banco - reversível."""
    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/bulk-status", methods=["POST"])
def atualizar_status_em_lote_instagram():
    corpo = request.json or {}
    novo_status = (corpo.get("status") or "").strip()

    lead_ids, erro = validar_ids_bulk(corpo.get("lead_ids"), "lead_id")
    if erro:
        return erro
    if novo_status not in STATUS_VALIDOS:
        return jsonify({"erro": f"status inválido: {novo_status}"}), 400

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/bulk-ignorar", methods=["POST"])
def ignorar_em_lote_instagram():
    lead_ids, erro = validar_ids_bulk((request.json or {}).get("lead_ids"), "lead_id")
    if erro:
        return erro

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/<int:lead_id>", methods=["DELETE"])
def excluir_lead_instagram_definitivamente(lead_id):
    """Apaga a linha do banco de vez. Só permite excluir leads já 'ignorado'
    (mesma proteção do CRM de Maps, contra apagar sem querer um lead ativo)."""
    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/bulk-excluir", methods=["POST"])
def excluir_em_lote_definitivamente_instagram():
    lead_ids, erro = validar_ids_bulk((request.json or {}).get("lead_ids"), "lead_id")
    if erro:
        return erro

    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/<int:lead_id>/observacoes", methods=["POST"])
def atualizar_observacoes_instagram(lead_id):
    texto = str((request.json or {}).get("observacoes", ""))
    if len(texto) > MAX_CARACTERES_OBSERVACOES_INSTAGRAM:
        return jsonify({"erro": f"observações muito longas (máximo {MAX_CARACTERES_OBSERVACOES_INSTAGRAM} caracteres)"}), 400

    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/<int:lead_id>/tags", methods=["POST"])
def atualizar_tags_instagram(lead_id):
    tags = str((request.json or {}).get("tags", ""))
    if len(tags) > MAX_CARACTERES_TAGS_INSTAGRAM:
        return jsonify({"erro": f"tags muito longas (máximo {MAX_CARACTERES_TAGS_INSTAGRAM} caracteres)"}), 400

    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/<int:lead_id>/followup", methods=["POST"])
def atualizar_followup_instagram(lead_id):
    data = (request.json or {}).get("proximo_followup") or None

    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/<int:lead_id>/marcar-followup-enviado", methods=["POST"])
def marcar_followup_enviado_instagram(lead_id):
    agora = datetime.now().isoformat(timespec="seconds")

    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/<int:lead_id>/desfazer-followup-enviado", methods=["POST"])
def desfazer_followup_enviado_instagram(lead_id):
    """Reverte um 'marcar follow-up enviado' feito por engano (versão Instagram)."""
    dados = request.json or {}
    follow_ups_enviados_anterior = dados.get("follow_ups_enviados_anterior")
    ultimo_followup_em_anterior = dados.get("ultimo_followup_em_anterior")
    proximo_followup_anterior = dados.get("proximo_followup_anterior")

    if follow_ups_enviados_anterior is None:
        return jsonify({"erro": "follow_ups_enviados_anterior é obrigatório"}), 400

    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/<int:lead_id>/sugestao-dm", methods=["POST"])
def salvar_sugestao_dm_instagram(lead_id):
    texto = str((request.json or {}).get("sugestao_dm", ""))
    if len(texto) > MAX_CARACTERES_SUGESTAO_DM:
        return jsonify({"erro": f"sugestão de DM muito longa (máximo {MAX_CARACTERES_SUGESTAO_DM} caracteres)"}), 400

    conexao = db.conectar()
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


@bp.route("/api/instagram/leads/<int:lead_id>/gerar-mensagem", methods=["POST"])
def gerar_mensagem_instagram(lead_id):
    corpo = request.json or {}
    tipo = corpo.get("tipo", "contato")
    forcar_nova = corpo.get("forcar_nova", False)
    if tipo not in ("contato", "followup"):
        return jsonify({"erro": "tipo inválido, use 'contato' ou 'followup'"}), 400

    conexao = db.conectar()
    try:
        lead = conexao.execute(
            "SELECT * FROM instagram_leads WHERE id = ?", (lead_id,)
        ).fetchone()

        if lead is None:
            return jsonify({"erro": "lead não encontrado"}), 404

        if tipo == "contato" and lead["sugestao_dm"] and not forcar_nova:
            return jsonify({"mensagem": lead["sugestao_dm"], "cache": True})

        try:
            mensagem, provedor_usado, avisos = ia.gerar_mensagem_instagram_com_fallback(
                username=lead["username"],
                full_name=lead["full_name"],
                biography=lead["biography"],
                nicho=lead["nicho"],
                justificativa=lead["justificativa"],
                tipo=tipo,
                follow_ups_enviados=lead["follow_ups_enviados"] or 0,
                # no follow-up a IA vê a DM já enviada, pra variar de verdade
                mensagem_anterior=lead["sugestao_dm"] if tipo == "followup" else None,
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


@bp.route("/api/instagram/nichos")
def listar_nichos_instagram():
    """Lista os valores distintos de nicho já preenchidos em instagram_leads, pra popular o filtro."""
    conexao = db.conectar()
    try:
        linhas = conexao.execute(
            "SELECT DISTINCT nicho FROM instagram_leads WHERE nicho IS NOT NULL AND nicho != '' ORDER BY nicho"
        ).fetchall()
    finally:
        conexao.close()

    return jsonify([linha["nicho"] for linha in linhas])


# ---------------------------------------------------------------------------
# Sessão do Instagram (login pela interface, sem linha de comando)
# ---------------------------------------------------------------------------

def _pasta_sessao_instagram():
    return paths.DIR_DADOS / "instagram" / "sessao"


def _sessao_instagram_atual():
    """Retorna (arquivo, usuario) da sessão salva, ou (None, None)."""
    arquivos = sorted(_pasta_sessao_instagram().glob("session-*.json"))
    if not arquivos:
        return None, None
    arquivo = arquivos[0]
    usuario = arquivo.stem.removeprefix("session-")
    return arquivo, usuario


@bp.route("/api/instagram/sessao")
def obter_sessao_instagram():
    _, usuario = _sessao_instagram_atual()
    return jsonify({"logada": bool(usuario), "usuario": usuario})


@bp.route("/api/instagram/sessao", methods=["DELETE"])
def encerrar_sessao_instagram():
    for arquivo in _pasta_sessao_instagram().glob("session-*.json"):
        arquivo.unlink()
    return jsonify({"ok": True})


@bp.route("/api/instagram/login", methods=["POST"])
def login_instagram():
    """Login pela interface. Se o Instagram exigir 2FA, responde precisa_2fa=True
    e o front reenvia a mesma requisição com codigo_2fa preenchido.

    A senha vive só nesta requisição - nunca é gravada, logada nem devolvida;
    o que fica em disco é o arquivo de sessão do instagrapi (mesmo formato do
    antigo login.py de linha de comando)."""
    dados = request.json or {}
    usuario = str(dados.get("usuario", "")).strip().lstrip("@")
    senha = str(dados.get("senha", ""))
    codigo_2fa = str(dados.get("codigo_2fa", "")).strip()

    if not usuario or not senha:
        return jsonify({"erro": "informe usuário e senha do Instagram"}), 400

    from instagrapi import Client
    from instagrapi.exceptions import TwoFactorRequired

    cliente = Client()
    try:
        if codigo_2fa:
            cliente.login(usuario, senha, verification_code=codigo_2fa)
        else:
            cliente.login(usuario, senha)
    except TwoFactorRequired:
        return jsonify({"precisa_2fa": True})
    except Exception as erro:
        # não logamos a senha em nenhuma hipótese; o tipo do erro basta pro diagnóstico
        logger.warning("login do instagram falhou para @%s (%s)", usuario, type(erro).__name__)
        return jsonify({"erro": f"O Instagram recusou o login: {erro}"}), 400

    pasta = _pasta_sessao_instagram()
    pasta.mkdir(parents=True, exist_ok=True)
    # sessão única: um login novo substitui qualquer sessão anterior
    for antigo in pasta.glob("session-*.json"):
        antigo.unlink()
    cliente.dump_settings(pasta / f"session-{usuario}.json")
    logger.info("sessão do instagram criada para @%s", usuario)
    return jsonify({"ok": True, "usuario": usuario})
