"""Rotas do CRM de leads do Google Maps: listagem, funil de status, tags,
observações, follow-up, geração de mensagem, exportação e disparo da busca."""

import csv
import io
import json
import logging
from datetime import date, datetime, timedelta

from flask import Blueprint, Response, jsonify, request

import db
import diagnostico
import ia
import jobs
import paths
import processar
from validacao import validar_ids_bulk
from constantes import (
    DIAS_PARA_LEAD_DIFICIL,
    MAX_AREAS_BUSCA_MAPA,
    MAX_CARACTERES_NICHO_BUSCA,
    MAX_CARACTERES_OBSERVACOES,
    MAX_CARACTERES_POR_LINHA_QUERY,
    MAX_CARACTERES_ROTULO_AREA,
    MAX_CARACTERES_TAGS,
    MAX_LINHAS_QUERIES_BUSCA,
    MAX_NICHOS_BUSCA_MAPA,
    RAIO_MAX_METROS,
    RAIO_MIN_METROS,
    STATUS_QUE_ENCERRAM_FOLLOWUP,
    STATUS_VALIDOS,
)

logger = logging.getLogger(__name__)

bp = Blueprint("leads", __name__)

LIMITE_PADRAO_LEADS = 30
LIMITE_MAXIMO_LEADS = 200


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


def calcular_score(nota, num_avaliacoes, site_status):
    """Score 0-100 pra ordenar a fila de abordagem: nota alta (0-40) + volume de
    avaliações como sinal de negócio estabelecido (0-30) + situação do site
    (sem site 30 > site ruim 22 > site ok 10 - quem nunca teve site tende a
    fechar mais rápido; site ok quase não é lead)."""
    pontos_nota = max(0.0, min((nota or 0) - 4.0, 1.0)) * 40
    pontos_avaliacoes = min(num_avaliacoes or 0, 100) * 0.3
    pontos_site = {"site_ruim": 22, "site_ok": 10}.get(site_status or "", 30)
    return round(pontos_nota + pontos_avaliacoes + pontos_site)


# mesma fórmula do calcular_score, em SQL - permite ordenar por score direto na
# query (a paginação exige que a ordenação aconteça no banco, não em Python)
SQL_SCORE = (
    "(MIN(MAX(COALESCE(nota, 0) - 4.0, 0), 1.0) * 40"
    " + MIN(COALESCE(num_avaliacoes, 0), 100) * 0.3"
    " + CASE COALESCE(site_status, '') WHEN 'site_ruim' THEN 22 WHEN 'site_ok' THEN 10 ELSE 30 END)"
)

SITUACOES_SITE_VALIDAS = {"sem_site", "site_ruim", "site_ok"}


def _enriquecer_lead_para_resposta(lead_dict):
    marcar_lead_dificil(lead_dict)
    lead_dict["score"] = calcular_score(
        lead_dict.get("nota"), lead_dict.get("num_avaliacoes"), lead_dict.get("site_status")
    )
    # o raio-X do site sai da API como objeto, não como string JSON
    try:
        lead_dict["site_checklist"] = (
            json.loads(lead_dict["site_checklist"]) if lead_dict.get("site_checklist") else None
        )
    except (TypeError, ValueError):
        lead_dict["site_checklist"] = None
    return lead_dict


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


@bp.route("/api/leads")
def listar_leads():
    """Lista os leads, com filtros opcionais via query string: status, nicho, nota_min, busca.
    Paginado via limit/offset (padrão: 30 por página). Resposta: {leads, tem_mais}."""
    status = request.args.get("status", "").strip()
    nicho = request.args.get("nicho", "").strip()
    nota_min_bruta = request.args.get("nota_min", "").strip()
    busca_texto = request.args.get("busca", "").strip()
    ordenar = request.args.get("ordenar", "").strip()
    if ordenar not in ("", "score"):
        return jsonify({"erro": f"ordenar inválido: {ordenar} (use 'score' ou omita)"}), 400
    site_status_filtro = request.args.get("site_status", "").strip()
    if site_status_filtro and site_status_filtro not in SITUACOES_SITE_VALIDAS:
        return jsonify({"erro": f"site_status inválido: {site_status_filtro}"}), 400
    followup_filtro = request.args.get("followup", "").strip()
    if followup_filtro not in ("", "vencido"):
        return jsonify({"erro": f"followup inválido: {followup_filtro} (use 'vencido' ou omita)"}), 400

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
    if site_status_filtro:
        condicoes.append("site_status = ?")
        parametros.append(site_status_filtro)
    if followup_filtro == "vencido":
        condicoes.append("proximo_followup IS NOT NULL AND proximo_followup <= ?")
        parametros.append(date.today().isoformat())

    sql = "SELECT * FROM leads"
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    if ordenar == "score":
        sql += f" ORDER BY {SQL_SCORE} DESC, nota DESC"
    elif followup_filtro == "vencido":
        sql += " ORDER BY proximo_followup ASC"  # mais atrasado primeiro
    else:
        sql += " ORDER BY visto_em DESC, nota DESC"
    sql += " LIMIT ? OFFSET ?"
    parametros_com_paginacao = [*parametros, limit + 1, offset]

    if not db.CAMINHO_BANCO.exists():
        return jsonify({"leads": [], "tem_mais": False})

    conexao = db.conectar()
    try:
        linhas = conexao.execute(sql, parametros_com_paginacao).fetchall()
    finally:
        conexao.close()

    tem_mais = len(linhas) > limit
    linhas = linhas[:limit]

    return jsonify({
        "leads": [_enriquecer_lead_para_resposta(db.linha_para_dict(linha)) for linha in linhas],
        "tem_mais": tem_mais,
    })


@bp.route("/api/nichos")
def listar_nichos():
    """Lista os valores distintos de nicho (já separado da cidade), pra popular o filtro."""
    if not db.CAMINHO_BANCO.exists():
        return jsonify([])

    conexao = db.conectar()
    try:
        linhas = conexao.execute(
            "SELECT DISTINCT nicho FROM leads WHERE nicho IS NOT NULL AND nicho != '' ORDER BY nicho"
        ).fetchall()
    finally:
        conexao.close()

    return jsonify([linha["nicho"] for linha in linhas])


@bp.route("/api/leads/<place_id>/status", methods=["POST"])
def atualizar_status(place_id):
    novo_status = (request.json or {}).get("status", "").strip()
    if novo_status not in STATUS_VALIDOS:
        return jsonify({"erro": f"status inválido: {novo_status}"}), 400

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = db.conectar()
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


@bp.route("/api/leads/<place_id>/historico")
def historico_lead(place_id):
    conexao = db.conectar()
    try:
        linhas = conexao.execute(
            "SELECT status_anterior, status_novo, alterado_em FROM historico_status "
            "WHERE place_id = ? ORDER BY alterado_em DESC",
            (place_id,),
        ).fetchall()
    finally:
        conexao.close()

    return jsonify([db.linha_para_dict(linha) for linha in linhas])


@bp.route("/api/leads/<place_id>/ignorar", methods=["POST"])
def ignorar_lead(place_id):
    """'Exclui' o lead da lista principal sem apagar do banco - ele nunca mais
    volta a aparecer, nem se a mesma busca for rodada de novo no futuro."""
    conexao = db.conectar()
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


@bp.route("/api/leads/bulk-status", methods=["POST"])
def atualizar_status_em_lote():
    """Muda o status de vários leads de uma vez, numa única transação."""
    corpo = request.json or {}
    novo_status = (corpo.get("status") or "").strip()

    place_ids, erro = validar_ids_bulk(corpo.get("place_ids"), "place_id")
    if erro:
        return erro
    if novo_status not in STATUS_VALIDOS:
        return jsonify({"erro": f"status inválido: {novo_status}"}), 400

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = db.conectar()
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


@bp.route("/api/leads/bulk-ignorar", methods=["POST"])
def ignorar_em_lote():
    """Marca vários leads como ignorados de uma vez, numa única transação."""
    place_ids, erro = validar_ids_bulk((request.json or {}).get("place_ids"), "place_id")
    if erro:
        return erro

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = db.conectar()
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


@bp.route("/api/leads/<place_id>", methods=["DELETE"])
def excluir_lead_definitivamente(place_id):
    """Apaga a linha do banco de vez - sem volta, sem histórico. Só permite excluir
    leads que já estão com status='ignorado' (proteção contra apagar sem querer um
    lead ativo direto pela API; excluir um ativo primeiro exige ignorá-lo)."""
    conexao = db.conectar()
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


@bp.route("/api/leads/bulk-excluir", methods=["POST"])
def excluir_em_lote_definitivamente():
    """Apaga várias linhas do banco de vez, numa única transação. Mesma proteção
    da versão individual: só apaga leads já 'ignorado', ignora silenciosamente
    qualquer place_id que não esteja nesse estado."""
    place_ids, erro = validar_ids_bulk((request.json or {}).get("place_ids"), "place_id")
    if erro:
        return erro

    conexao = db.conectar()
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


@bp.route("/api/leads/<place_id>/observacoes", methods=["POST"])
def atualizar_observacoes(place_id):
    texto = str((request.json or {}).get("observacoes", ""))
    if len(texto) > MAX_CARACTERES_OBSERVACOES:
        return jsonify({"erro": f"observações muito longas (máximo {MAX_CARACTERES_OBSERVACOES} caracteres)"}), 400

    conexao = db.conectar()
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


@bp.route("/api/leads/<place_id>/tags", methods=["POST"])
def atualizar_tags(place_id):
    tags = str((request.json or {}).get("tags", ""))
    if len(tags) > MAX_CARACTERES_TAGS:
        return jsonify({"erro": f"tags muito longas (máximo {MAX_CARACTERES_TAGS} caracteres)"}), 400

    conexao = db.conectar()
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


@bp.route("/api/leads/<place_id>/followup", methods=["POST"])
def atualizar_followup(place_id):
    data = (request.json or {}).get("proximo_followup") or None

    conexao = db.conectar()
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


@bp.route("/api/leads/<place_id>/gerar-mensagem", methods=["POST"])
def gerar_mensagem(place_id):
    corpo = request.json or {}
    forcar_nova = corpo.get("forcar_nova", False)
    tipo = corpo.get("tipo", "contato")
    if tipo not in ("contato", "followup"):
        return jsonify({"erro": "tipo inválido, use 'contato' ou 'followup'"}), 400

    conexao = db.conectar()
    try:
        lead = conexao.execute("SELECT * FROM leads WHERE place_id = ?", (place_id,)).fetchone()

        if lead is None:
            return jsonify({"erro": "lead não encontrado"}), 404

        if tipo == "contato" and lead["mensagem_gerada"] and not forcar_nova:
            return jsonify({"mensagem": lead["mensagem_gerada"], "cache": True})

        # lead com site: captura o conteúdo real pra copy citar um detalhe específico,
        # e anexa o raio-X (tem/falta) já salvo na busca
        conteudo_site = None
        if tipo == "contato" and lead["site_url"]:
            conteudo_site = processar.capturar_conteudo_site(lead["site_url"])
            try:
                checklist = json.loads(lead["site_checklist"]) if lead["site_checklist"] else None
            except (TypeError, ValueError):
                checklist = None
            if checklist and checklist.get("falta"):
                resumo_raio_x = (
                    "Raio-X do site (dados reais): TEM "
                    + (", ".join(checklist.get("tem", [])) or "quase nada")
                    + "; FALTA " + ", ".join(checklist["falta"]) + "."
                )
                conteudo_site = f"{conteudo_site}\n{resumo_raio_x}" if conteudo_site else resumo_raio_x

        try:
            mensagem, provedor_usado, avisos = ia.gerar_mensagem_com_fallback(
                nome=lead["nome"],
                categoria=lead["categoria"],
                endereco=lead["endereco"],
                nota=lead["nota"],
                tipo=tipo,
                follow_ups_enviados=lead["follow_ups_enviados"] or 0,
                site_status=lead["site_status"],
                site_problemas=lead["site_problemas"],
                num_avaliacoes=lead["num_avaliacoes"],
                cidade=lead["cidade"],
                instagram_url=lead["instagram_url"],
                # no follow-up a IA vê a mensagem já enviada, pra variar de verdade
                mensagem_anterior=lead["mensagem_gerada"] if tipo == "followup" else None,
                conteudo_site=conteudo_site,
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


@bp.route("/api/leads/<place_id>/marcar-followup-enviado", methods=["POST"])
def marcar_followup_enviado(place_id):
    agora = datetime.now().isoformat(timespec="seconds")

    conexao = db.conectar()
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


@bp.route("/api/leads/<place_id>/desfazer-followup-enviado", methods=["POST"])
def desfazer_followup_enviado(place_id):
    """Reverte um 'marcar follow-up enviado' feito por engano, restaurando os
    valores anteriores enviados pelo cliente (capturados antes da marcação)."""
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


@bp.route("/api/leads/<place_id>/reanalisar-site", methods=["POST"])
def reanalisar_site(place_id):
    """Re-roda a análise do site na hora: atualiza status, problemas e o raio-X.
    Lead sem site tenta achar o site de novo na busca web. Se o site melhorou,
    o lead vira 'site_ok' (honestidade > manter a venda)."""
    conexao = db.conectar()
    try:
        lead = conexao.execute("SELECT * FROM leads WHERE place_id = ?", (place_id,)).fetchone()
    finally:
        conexao.close()
    if lead is None:
        return jsonify({"erro": "lead não encontrado"}), 404

    site_url = lead["site_url"] or processar.buscar_site_da_empresa(
        lead["nome"], lead["endereco"] or lead["cidade"] or ""
    )

    if not site_url:
        novo_status, problemas_texto, checklist = "sem_site", None, None
    else:
        situacao, problemas, checklist = processar.avaliar_site_completo(site_url)
        novo_status = "site_ok" if situacao == "ok" else "site_ruim"
        problemas_texto = "; ".join(problemas) or None

    agora = datetime.now().isoformat(timespec="seconds")
    conexao = db.conectar()
    try:
        conexao.execute(
            "UPDATE leads SET site_url = ?, site_status = ?, site_problemas = ?, "
            "site_checklist = ?, atualizado_em = ? WHERE place_id = ?",
            (
                site_url,
                novo_status,
                problemas_texto,
                json.dumps(checklist, ensure_ascii=False) if checklist else None,
                agora,
                place_id,
            ),
        )
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({
        "ok": True,
        "site_url": site_url,
        "site_status": novo_status,
        "site_problemas": problemas_texto,
        "site_checklist": checklist,
    })


@bp.route("/api/buscar/historico")
def historico_buscas():
    """Últimas buscas do Maps (da tabela jobs): quando rodou, como terminou e a
    mensagem final com as contagens - responde 'onde eu já busquei?'."""
    conexao = db.conectar()
    try:
        buscas = [
            db.linha_para_dict(l) for l in conexao.execute(
                "SELECT id, status, mensagem, progresso_atual, progresso_total, "
                "iniciado_em, finalizado_em FROM jobs WHERE tipo = 'busca_maps' "
                "ORDER BY id DESC LIMIT 15"
            ).fetchall()
        ]
    finally:
        conexao.close()
    return jsonify({"buscas": buscas})


@bp.route("/api/leads/<place_id>/diagnostico.pdf")
def baixar_diagnostico(place_id):
    """Diagnóstico de presença digital em PDF - pronto para anexar no WhatsApp.
    Quando o lead tem site, inclui a nota oficial do PageSpeed (pode levar ~30s)."""
    conexao = db.conectar()
    try:
        lead = conexao.execute("SELECT * FROM leads WHERE place_id = ?", (place_id,)).fetchone()
    finally:
        conexao.close()

    if lead is None:
        return jsonify({"erro": "lead não encontrado"}), 404

    pdf_bytes = diagnostico.gerar_diagnostico_pdf(lead)
    resposta = Response(pdf_bytes, mimetype="application/pdf")
    resposta.headers["Content-Disposition"] = (
        f'attachment; filename="{diagnostico.nome_arquivo_diagnostico(lead["nome"])}"'
    )
    return resposta


@bp.route("/api/exportar")
def exportar_csv():
    """Exporta os leads (respeitando os mesmos filtros da tela) num CSV completo pra download."""
    status = request.args.get("status", "").strip()
    nicho = request.args.get("nicho", "").strip()
    site_status_filtro = request.args.get("site_status", "").strip()

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
    if site_status_filtro in SITUACOES_SITE_VALIDAS:
        condicoes.append("site_status = ?")
        parametros.append(site_status_filtro)

    sql = "SELECT * FROM leads"
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    sql += " ORDER BY visto_em DESC, nota DESC"

    conexao = db.conectar()
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
            "site_status", "site_url", "site_problemas", "instagram_url",
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
                lead["site_status"] or "sem_site",
                lead["site_url"] or "",
                lead["site_problemas"] or "",
                lead["instagram_url"] or "",
            ]
        )

    resposta = Response(saida.getvalue(), mimetype="text/csv; charset=utf-8")
    resposta.headers["Content-Disposition"] = "attachment; filename=leads_exportados.csv"
    return resposta


def _validar_busca_por_texto(corpo):
    """Modo clássico: 'nicho em cidade', uma busca por linha.
    Retorna (queries_texto, None) ou (None, resposta_de_erro)."""
    queries_texto = corpo.get("queries", "").strip()
    if not queries_texto:
        return None, (jsonify({"erro": "informe ao menos um nicho + cidade"}), 400)

    linhas_queries = [linha for linha in queries_texto.splitlines() if linha.strip()]
    if len(linhas_queries) > MAX_LINHAS_QUERIES_BUSCA:
        return None, (jsonify({
            "erro": f"no máximo {MAX_LINHAS_QUERIES_BUSCA} linhas por busca (você enviou {len(linhas_queries)})"
        }), 400)
    linha_longa_demais = next(
        (linha for linha in linhas_queries if len(linha) > MAX_CARACTERES_POR_LINHA_QUERY), None
    )
    if linha_longa_demais:
        return None, (jsonify({
            "erro": f"uma das linhas passa de {MAX_CARACTERES_POR_LINHA_QUERY} caracteres: "
                    f"\"{linha_longa_demais[:60]}...\""
        }), 400)

    return queries_texto, None


def _validar_busca_por_mapa(corpo):
    """Modo mapa: lista de nichos + lista de áreas (pino com lat/lng/raio/rótulo).
    Retorna ((queries_texto, areas_limpas), None) ou (None, resposta_de_erro)."""
    nichos_brutos = corpo.get("nichos")
    areas_brutas = corpo.get("areas")

    if not isinstance(nichos_brutos, list) or not nichos_brutos:
        return None, (jsonify({"erro": "informe ao menos um nicho (ex: clínica de estética)"}), 400)
    if len(nichos_brutos) > MAX_NICHOS_BUSCA_MAPA:
        return None, (jsonify({"erro": f"no máximo {MAX_NICHOS_BUSCA_MAPA} nichos por busca"}), 400)

    nichos = []
    for nicho in nichos_brutos:
        texto = str(nicho or "").strip()
        if not texto:
            continue
        if len(texto) > MAX_CARACTERES_NICHO_BUSCA:
            return None, (jsonify({"erro": f"nicho muito longo (máximo {MAX_CARACTERES_NICHO_BUSCA} caracteres): \"{texto[:40]}...\""}), 400)
        nichos.append(texto)
    if not nichos:
        return None, (jsonify({"erro": "informe ao menos um nicho (ex: clínica de estética)"}), 400)

    if not isinstance(areas_brutas, list) or not areas_brutas:
        return None, (jsonify({"erro": "adicione ao menos um pino no mapa"}), 400)
    if len(areas_brutas) > MAX_AREAS_BUSCA_MAPA:
        return None, (jsonify({"erro": f"no máximo {MAX_AREAS_BUSCA_MAPA} áreas (pinos) por busca"}), 400)

    areas = []
    for indice, area in enumerate(areas_brutas, start=1):
        if not isinstance(area, dict):
            return None, (jsonify({"erro": f"área {indice} inválida"}), 400)
        try:
            lat = float(area.get("lat"))
            lng = float(area.get("lng"))
            raio_m = int(area.get("raio_m"))
        except (TypeError, ValueError):
            return None, (jsonify({"erro": f"área {indice}: lat/lng/raio_m inválidos"}), 400)

        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return None, (jsonify({"erro": f"área {indice}: coordenadas fora do intervalo válido"}), 400)
        if not (RAIO_MIN_METROS <= raio_m <= RAIO_MAX_METROS):
            return None, (jsonify({
                "erro": f"área {indice}: raio deve ficar entre {RAIO_MIN_METROS} m e {RAIO_MAX_METROS // 1000} km"
            }), 400)

        rotulo = str(area.get("rotulo") or "").strip()[:MAX_CARACTERES_ROTULO_AREA]
        if not rotulo:
            rotulo = f"{lat:.4f}, {lng:.4f}"

        areas.append({"lat": lat, "lng": lng, "raio_m": raio_m, "rotulo": rotulo})

    return ("\n".join(nichos), areas), None


@bp.route("/api/buscar", methods=["POST"])
def disparar_busca():
    """Dispara a busca no Maps em um de dois modos:
    - texto (legado): {"queries": "nicho em cidade\\n..."}
    - mapa: {"nichos": [...], "areas": [{lat, lng, raio_m, rotulo}, ...]} -
      o scraper roda uma vez por área, geolocalizado no pino com o raio escolhido."""
    corpo = request.json or {}
    modo_mapa = "areas" in corpo or "nichos" in corpo

    if modo_mapa:
        resultado, erro = _validar_busca_por_mapa(corpo)
        if erro:
            return erro
        queries_texto, areas = resultado
    else:
        queries_texto, erro = _validar_busca_por_texto(corpo)
        if erro:
            return erro
        areas = None

    if not jobs.tentar_reservar_busca():
        return jsonify({"erro": "já existe uma busca em andamento"}), 409

    try:
        # queries.txt é escrito a cada busca - vai pra área de dados (gravável)
        caminho_queries = paths.caminho_dados("queries.txt", criar_pai=True)
        caminho_queries.write_text(queries_texto + "\n", encoding="utf-8")
        jobs.iniciar_thread_busca(areas)
    except Exception:
        jobs.liberar_busca()  # senão a flag ficaria presa em True pra sempre
        raise

    return jsonify({"ok": True})


@bp.route("/api/buscar/status")
def status_busca():
    return jsonify(jobs.obter_status_busca())
