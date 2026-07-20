"""Rotas de configuração (chaves de IA, proxies do scraper) e de templates de mensagem."""

from datetime import datetime

from flask import Blueprint, jsonify, request

import db
from constantes import MAX_CARACTERES_TEXTO_TEMPLATE, MAX_CARACTERES_TITULO_TEMPLATE

bp = Blueprint("config", __name__)

LINKS_OBTER_CHAVE = {
    "gemini": "https://aistudio.google.com/apikey",
    "groq": "https://console.groq.com/keys",
    "nvidia": "https://build.nvidia.com",
    "pagespeed": "https://developers.google.com/speed/docs/insights/v5/get-started",
    "places": "https://console.cloud.google.com/apis/credentials",
}


def mascarar_chave(valor):
    if not valor:
        return None
    if len(valor) <= 4:
        return "•" * len(valor)
    return "•" * 8 + valor[-4:]


@bp.route("/api/configuracoes")
def listar_configuracoes():
    resposta = {}
    for chave in db.CHAVES_CONFIG_VALIDAS:
        valor = db.obter_config(chave)
        resposta[chave] = {
            "configurada": bool(valor),
            "mascarada": mascarar_chave(valor),
            "link_obter_chave": LINKS_OBTER_CHAVE[chave],
        }
    return jsonify(resposta)


@bp.route("/api/configuracoes", methods=["POST"])
def atualizar_configuracao():
    dados = request.json or {}
    chave = dados.get("chave", "")
    valor = str(dados.get("valor", "")).strip()

    if chave not in db.CHAVES_CONFIG_VALIDAS:
        return jsonify({"erro": f"chave inválida. Use uma de: {', '.join(db.CHAVES_CONFIG_VALIDAS)}"}), 400
    if not valor:
        return jsonify({"erro": "informe um valor para a chave de API"}), 400

    db.salvar_config(chave, valor)
    return jsonify({"ok": True, "mascarada": mascarar_chave(valor)})


# ---------------------------------------------------------------------------
# Fonte de dados do Google Maps (scraper local vs Places API oficial)
# ---------------------------------------------------------------------------

FONTES_MAPS_VALIDAS = {"scraper", "places"}


@bp.route("/api/configuracoes/fonte-maps")
def obter_fonte_maps():
    chave = db.obter_config("places")
    return jsonify({
        "fonte": db.obter_config("fonte_maps") or "scraper",
        "chave_configurada": bool(chave),
        "mascarada": mascarar_chave(chave),
        "link_obter_chave": LINKS_OBTER_CHAVE["places"],
    })


@bp.route("/api/configuracoes/fonte-maps", methods=["POST"])
def salvar_fonte_maps():
    """Valida (com uma busca real mínima) e salva a fonte escolhida.
    A mudança vale apenas para novas buscas."""
    import fontes_maps

    dados = request.json or {}
    fonte = str(dados.get("fonte", "")).strip()
    chave_nova = str(dados.get("chave", "")).strip()

    if fonte not in FONTES_MAPS_VALIDAS:
        return jsonify({"erro": f"fonte inválida. Use uma de: {', '.join(sorted(FONTES_MAPS_VALIDAS))}"}), 400

    if fonte == "places":
        chave = chave_nova or db.obter_config("places")
        if not chave:
            return jsonify({"erro": "informe a chave da Google Places API para usar essa fonte"}), 400
        ok, erro = fontes_maps.validar_chave_places(chave)
        if not ok:
            return jsonify({"erro": erro}), 400
        if chave_nova:
            db.salvar_config("places", chave_nova)

    db.salvar_config("fonte_maps", fonte)
    return jsonify({
        "ok": True,
        "fonte": fonte,
        "chave_configurada": bool(db.obter_config("places")),
        "mascarada": mascarar_chave(db.obter_config("places")),
    })


CAMPOS_PERFIL_VENDEDOR = {
    "vendedor_nome": 80,
    "vendedor_apresentacao": 300,
    "vendedor_diferencial": 300,
}


@bp.route("/api/configuracoes/perfil-vendedor")
def obter_perfil_vendedor():
    """Perfil de quem envia as mensagens - injetado no system prompt da IA para
    as copies saírem assinadas e na voz certa (Configurações → Seu perfil)."""
    return jsonify({
        "nome": db.obter_config("vendedor_nome") or "",
        "apresentacao": db.obter_config("vendedor_apresentacao") or "",
        "diferencial": db.obter_config("vendedor_diferencial") or "",
    })


@bp.route("/api/configuracoes/perfil-vendedor", methods=["POST"])
def salvar_perfil_vendedor():
    dados = request.json or {}
    valores = {
        "vendedor_nome": str(dados.get("nome", "")).strip(),
        "vendedor_apresentacao": str(dados.get("apresentacao", "")).strip(),
        "vendedor_diferencial": str(dados.get("diferencial", "")).strip(),
    }
    for chave, maximo in CAMPOS_PERFIL_VENDEDOR.items():
        if len(valores[chave]) > maximo:
            return jsonify({"erro": f"campo muito longo (máximo {maximo} caracteres)"}), 400

    for chave, valor in valores.items():
        db.salvar_config(chave, valor)

    return jsonify({"ok": True})


@bp.route("/api/configuracoes/scraper-proxies")
def obter_proxies_scraper():
    proxies = db.obter_config("scraper_proxies") or ""
    return jsonify({"configurado": bool(proxies), "proxies": proxies})


@bp.route("/api/configuracoes/scraper-proxies", methods=["POST"])
def salvar_proxies_scraper():
    """Salva a lista de proxies (opcional) usada pelo google-maps-scraper.exe -
    formato aceito pelo scraper: protocol://user:pass@host:port, separados por
    vírgula. Útil quando o Google bloqueia buscas repetidas vindas do mesmo IP."""
    dados = request.json or {}
    proxies = str(dados.get("proxies", "")).strip()
    db.salvar_config("scraper_proxies", proxies)
    return jsonify({"ok": True, "configurado": bool(proxies)})


@bp.route("/api/templates")
def listar_templates():
    """Lista templates de mensagem, com filtro opcional por nicho via query string."""
    nicho = request.args.get("nicho", "").strip()

    sql = "SELECT * FROM templates_mensagem"
    parametros = []
    if nicho:
        sql += " WHERE nicho = ?"
        parametros.append(nicho)
    sql += " ORDER BY vezes_usado DESC, atualizado_em DESC"

    conexao = db.conectar()
    try:
        templates = [db.linha_para_dict(l) for l in conexao.execute(sql, parametros).fetchall()]
    finally:
        conexao.close()

    return jsonify({"templates": templates})


@bp.route("/api/templates", methods=["POST"])
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
    conexao = db.conectar()
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


@bp.route("/api/templates/<int:template_id>", methods=["PUT"])
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

    conexao = db.conectar()
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


@bp.route("/api/templates/<int:template_id>", methods=["DELETE"])
def excluir_template(template_id):
    conexao = db.conectar()
    try:
        cursor = conexao.execute("DELETE FROM templates_mensagem WHERE id = ?", (template_id,))
        conexao.commit()
        if cursor.rowcount == 0:
            return jsonify({"erro": "template não encontrado"}), 404
    finally:
        conexao.close()

    return jsonify({"ok": True})


@bp.route("/api/templates/<int:template_id>/usar", methods=["POST"])
def registrar_uso_template(template_id):
    """Incrementa o contador de uso do template (chamado quando o usuário usa
    o template como base pra uma mensagem de abordagem)."""
    conexao = db.conectar()
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
