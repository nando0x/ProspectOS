"""Cockpit de conversa: histórico de mensagens por lead e análise da negociação por IA.

Como as peças se encaixam:
- O histórico é uma tabela única (`mensagens_conversa`) que serve os dois canais,
  endereçada por (canal, lead_ref) - as PKs dos dois canais são incompatíveis
  (place_id TEXT vs id INTEGER), então não há FK real.
- As mensagens chegam por três caminhos: capturadas da janela do WhatsApp
  (origem "whatsapp"), digitadas à mão no cockpit ("manual"), ou registradas
  pelo app quando o usuário envia a partir dele ("app").
- A ingestão do WhatsApp é PASSIVA: a janela só reporta o que já está na tela do
  chat que o usuário abriu. O vínculo com o lead é feito pelo telefone, nunca por
  adivinhação: número que não casa com nenhum lead é descartado silenciosamente.
"""

import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime

from flask import Blueprint, jsonify, request

import db
import ia
from constantes import (
    AUTORES_MENSAGEM,
    CANAIS_CONVERSA,
    MAX_CARACTERES_MENSAGEM_CONVERSA,
    MAX_MENSAGENS_POR_INGESTAO,
    MAX_MENSAGENS_POR_LEAD,
    ORIGENS_MENSAGEM,
)

logger = logging.getLogger(__name__)

bp = Blueprint("conversa", __name__)

# Lead cuja conversa está aberta na janela do WhatsApp. Vive em memória (igual
# ao estado dos jobs): é um app local de um usuário só, e perder isso num
# restart não custa nada - o vínculo por telefone é a fonte da verdade.
_lead_ativo = {"canal": None, "lead_ref": None, "telefone": None, "nome": None}

# Sinal de vida da janela do WhatsApp: atualizado a cada ingestão/aviso vindo do
# leitor passivo. Mais velho que SEGUNDOS_CAPTURA_VIVA = captura parada.
SEGUNDOS_CAPTURA_VIVA = 40
_estado_captura = {"visto_em": None, "telefone": None, "seletores_ok": True, "detalhe": None}


def _marcar_captura_viva(telefone=None, seletores_ok=True, detalhe=None):
    _estado_captura.update({
        "visto_em": _agora(),
        "telefone": telefone or _estado_captura["telefone"],
        "seletores_ok": seletores_ok,
        "detalhe": detalhe,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _agora():
    return datetime.now().isoformat(timespec="seconds")


def normalizar_telefone(bruto):
    """Forma canônica pra comparar números: só dígitos, sem o DDI 55.

    O banco guarda "65996757327" (DDD + número) e o WhatsApp reporta
    "5565996757327" - sem normalizar os dois lados, nenhum número casaria."""
    digitos = re.sub(r"\D", "", bruto or "")
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]
    return digitos or None


def _variantes_telefone(bruto):
    """Todas as formas com que o mesmo número pode aparecer, por causa do 9º
    dígito: leads capturados antigos podem estar com 10 dígitos (DDD + 8)
    enquanto o WhatsApp resolve o JID com 11 (DDD + 9 + 8), e vice-versa.
    Comparar só a forma canônica erraria justamente os leads mais antigos."""
    canonico = normalizar_telefone(bruto)
    if not canonico:
        return set()

    variantes = {canonico}
    ddd, resto = canonico[:2], canonico[2:]
    if len(resto) == 9 and resto.startswith("9"):
        variantes.add(ddd + resto[1:])  # sem o nono dígito
    elif len(resto) == 8:
        variantes.add(ddd + "9" + resto)  # com o nono dígito
    return variantes


def _validar_alvo(canal, lead_ref):
    """Confere canal válido e lead existente. Retorna (lead_dict, None) ou
    (None, (resposta, status))."""
    if canal not in CANAIS_CONVERSA:
        return None, (jsonify({"erro": f"canal inválido. Use um de: {', '.join(sorted(CANAIS_CONVERSA))}"}), 400)

    conexao = db.conectar()
    try:
        if canal == "maps":
            linha = conexao.execute("SELECT * FROM leads WHERE place_id = ?", (lead_ref,)).fetchone()
        else:
            try:
                lead_id = int(lead_ref)
            except (TypeError, ValueError):
                return None, (jsonify({"erro": "lead do Instagram é identificado por um número"}), 400)
            linha = conexao.execute("SELECT * FROM instagram_leads WHERE id = ?", (lead_id,)).fetchone()
    finally:
        conexao.close()

    if not linha:
        return None, (jsonify({"erro": "lead não encontrado"}), 404)
    return dict(linha), None


def _chave_dedup(autor, texto, enviada_em, id_externo=None):
    """Identidade estável de uma mensagem capturada. Usa o id do próprio
    WhatsApp quando disponível (mais confiável); senão, o hash do conteúdo +
    horário, que é o que distingue duas mensagens iguais enviadas em momentos
    diferentes."""
    if id_externo:
        return f"wa:{id_externo}"
    bruto = f"{autor}|{(texto or '').strip()}|{enviada_em or ''}"
    return "h:" + hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:24]


def _listar_mensagens(conexao, canal, lead_ref):
    linhas = conexao.execute(
        "SELECT id, autor, texto, enviada_em, origem FROM mensagens_conversa "
        "WHERE canal = ? AND lead_ref = ? ORDER BY enviada_em, id",
        (canal, str(lead_ref)),
    ).fetchall()
    return [dict(linha) for linha in linhas]


def _inserir_mensagem(conexao, canal, lead_ref, autor, texto, enviada_em, origem, chave_dedup):
    """Insere ignorando duplicata (UNIQUE em canal+lead_ref+chave_dedup).
    Retorna True se gravou de fato."""
    cursor = conexao.execute(
        "INSERT OR IGNORE INTO mensagens_conversa "
        "(canal, lead_ref, autor, texto, enviada_em, origem, chave_dedup, criada_em) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (canal, str(lead_ref), autor, texto, enviada_em, origem, chave_dedup, _agora()),
    )
    return cursor.rowcount > 0


def _ultima_analise(conexao, canal, lead_ref):
    linha = conexao.execute(
        "SELECT estagio, leitura, objetivo, resposta_sugerida, evitar, provedor, "
        "mensagens_consideradas, criada_em FROM analises_conversa "
        "WHERE canal = ? AND lead_ref = ? ORDER BY id DESC LIMIT 1",
        (canal, str(lead_ref)),
    ).fetchone()
    if not linha:
        return None
    analise = dict(linha)
    try:
        analise["evitar"] = json.loads(analise["evitar"] or "[]")
    except (TypeError, json.JSONDecodeError):
        analise["evitar"] = []
    return analise


# ---------------------------------------------------------------------------
# Histórico da conversa
# ---------------------------------------------------------------------------

@bp.route("/api/conversa/<canal>/<path:lead_ref>/mensagens")
def listar_mensagens(canal, lead_ref):
    _lead, erro = _validar_alvo(canal, lead_ref)
    if erro:
        return erro

    conexao = db.conectar()
    try:
        return jsonify({
            "mensagens": _listar_mensagens(conexao, canal, lead_ref),
            "analise": _ultima_analise(conexao, canal, lead_ref),
        })
    finally:
        conexao.close()


@bp.route("/api/conversa/<canal>/<path:lead_ref>/mensagens", methods=["POST"])
def adicionar_mensagem(canal, lead_ref):
    """Registra uma mensagem à mão. É a rede de segurança do cockpit: funciona
    no navegador (sem Electron) e quando a captura do WhatsApp falha."""
    _lead, erro = _validar_alvo(canal, lead_ref)
    if erro:
        return erro

    dados = request.json or {}
    autor = str(dados.get("autor", "")).strip().lower()
    texto = str(dados.get("texto", "")).strip()
    origem = str(dados.get("origem", "manual")).strip().lower()

    if autor not in AUTORES_MENSAGEM:
        return jsonify({"erro": f"autor inválido. Use um de: {', '.join(sorted(AUTORES_MENSAGEM))}"}), 400
    if not texto:
        return jsonify({"erro": "a mensagem não pode ficar vazia"}), 400
    if len(texto) > MAX_CARACTERES_MENSAGEM_CONVERSA:
        return jsonify({"erro": f"mensagem muito longa (máximo {MAX_CARACTERES_MENSAGEM_CONVERSA} caracteres)"}), 400
    if origem not in ORIGENS_MENSAGEM:
        origem = "manual"

    enviada_em = str(dados.get("enviada_em") or _agora())
    conexao = db.conectar()
    try:
        total = conexao.execute(
            "SELECT COUNT(*) FROM mensagens_conversa WHERE canal = ? AND lead_ref = ?",
            (canal, str(lead_ref)),
        ).fetchone()[0]
        if total >= MAX_MENSAGENS_POR_LEAD:
            return jsonify({"erro": "esta conversa atingiu o limite de mensagens guardadas"}), 400

        # mensagem manual não participa da dedup automática (chave NULL): duas
        # iguais digitadas de propósito devem coexistir
        _inserir_mensagem(conexao, canal, lead_ref, autor, texto, enviada_em, origem, None)
        conexao.commit()
        return jsonify({"ok": True, "mensagens": _listar_mensagens(conexao, canal, lead_ref)})
    finally:
        conexao.close()


@bp.route("/api/conversa/<canal>/<path:lead_ref>/mensagens/<int:mensagem_id>", methods=["DELETE"])
def remover_mensagem(canal, lead_ref, mensagem_id):
    """Apaga uma mensagem do histórico (captura errada, teste, duplicata)."""
    _lead, erro = _validar_alvo(canal, lead_ref)
    if erro:
        return erro

    conexao = db.conectar()
    try:
        conexao.execute(
            "DELETE FROM mensagens_conversa WHERE id = ? AND canal = ? AND lead_ref = ?",
            (mensagem_id, canal, str(lead_ref)),
        )
        conexao.commit()
        return jsonify({"ok": True, "mensagens": _listar_mensagens(conexao, canal, lead_ref)})
    finally:
        conexao.close()


# ---------------------------------------------------------------------------
# Análise da negociação por IA
# ---------------------------------------------------------------------------

@bp.route("/api/conversa/<canal>/<path:lead_ref>/analisar", methods=["POST"])
def analisar_conversa(canal, lead_ref):
    lead, erro = _validar_alvo(canal, lead_ref)
    if erro:
        return erro

    conexao = db.conectar()
    try:
        mensagens = _listar_mensagens(conexao, canal, lead_ref)
    finally:
        conexao.close()

    if not mensagens:
        return jsonify({
            "erro": "ainda não há mensagens nesta conversa. Registre ao menos a resposta do lead "
                    "para a IA ter o que analisar."
        }), 400

    try:
        analise, provedor, avisos = ia.analisar_conversa_com_fallback(lead, mensagens)
    except ia.NenhumProvedorDisponivel as excecao:
        logger.warning("análise de conversa falhou em todos os provedores: %s", excecao.erro_final)
        return jsonify({
            "erro": "Nenhum provedor de IA conseguiu analisar a conversa agora. "
                    "Confira suas chaves em Configurações e tente de novo."
        }), 500
    except Exception as erro_inesperado:
        logger.exception("erro inesperado ao analisar conversa")
        return jsonify({"erro": str(erro_inesperado)}), 500

    conexao = db.conectar()
    try:
        conexao.execute(
            "INSERT INTO analises_conversa (canal, lead_ref, estagio, leitura, objetivo, "
            "resposta_sugerida, evitar, provedor, mensagens_consideradas, criada_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                canal, str(lead_ref), analise["estagio"], analise["leitura"], analise["objetivo"],
                analise["resposta_sugerida"], json.dumps(analise["evitar"], ensure_ascii=False),
                provedor, len(mensagens), _agora(),
            ),
        )
        conexao.commit()
    finally:
        conexao.close()

    return jsonify({**analise, "provedor": provedor, "avisos": avisos,
                    "mensagens_consideradas": len(mensagens)})


# ---------------------------------------------------------------------------
# Vínculo com a janela do WhatsApp (lead ativo + ingestão passiva)
# ---------------------------------------------------------------------------

@bp.route("/api/conversa/lead-ativo", methods=["POST"])
def definir_lead_ativo():
    """Chamado quando o usuário abre o WhatsApp a partir de um lead: guarda quem
    é o dono da conversa que está prestes a aparecer na janela."""
    dados = request.json or {}
    canal = str(dados.get("canal", "maps")).strip().lower()
    lead_ref = str(dados.get("lead_ref", "")).strip()
    if not lead_ref:
        return jsonify({"erro": "informe o lead"}), 400

    lead, erro = _validar_alvo(canal, lead_ref)
    if erro:
        return erro

    _lead_ativo.update({
        "canal": canal,
        "lead_ref": lead_ref,
        "telefone": normalizar_telefone(lead.get("telefone") or lead.get("whatsapp_link")),
        "nome": lead.get("nome") or lead.get("username"),
    })
    return jsonify({"ok": True, **_lead_ativo})


@bp.route("/api/conversa/lead-ativo")
def obter_lead_ativo():
    return jsonify(dict(_lead_ativo))


def _resolver_lead_por_telefone(telefone):
    """Descobre a qual lead pertence um número. O telefone é a fonte da verdade:
    se o usuário trocar de conversa dentro da janela do WhatsApp, as mensagens
    ainda caem no lead certo. Retorna (canal, lead_ref) ou (None, None)."""
    variantes = _variantes_telefone(telefone)
    if not variantes:
        return None, None

    if _lead_ativo["telefone"] and _lead_ativo["telefone"] in variantes:
        return _lead_ativo["canal"], _lead_ativo["lead_ref"]

    conexao = db.conectar()
    try:
        # compara já normalizado dos dois lados: o banco guarda com máscara em
        # alguns casos e o WhatsApp sempre manda com DDI
        for linha in conexao.execute(
            "SELECT place_id, telefone FROM leads WHERE telefone IS NOT NULL AND telefone != ''"
        ):
            if _variantes_telefone(linha["telefone"]) & variantes:
                return "maps", linha["place_id"]
    finally:
        conexao.close()
    return None, None


@bp.route("/api/conversa/estado-captura")
def obter_estado_captura():
    """Diz se a leitura do WhatsApp está viva. A interface usa isto (e não a
    presença do Electron) pra escolher entre modo automático e manual: cobre
    também o caso "estou no app, mas fechei a janela do WhatsApp"."""
    visto_em = _estado_captura["visto_em"]
    viva = False
    if visto_em:
        idade = (datetime.now() - datetime.fromisoformat(visto_em)).total_seconds()
        viva = idade <= SEGUNDOS_CAPTURA_VIVA
    return jsonify({**_estado_captura, "ativa": viva})


@bp.route("/api/conversa/ingestao", methods=["POST"])
def ingerir_mensagens_do_whatsapp():
    """Recebe o lote de mensagens lido passivamente da janela do WhatsApp.

    Nunca cria lead nem adivinha dono: número que não casa com nenhum lead é
    ignorado (`vinculado: false`), e o cockpit avisa o usuário em vez de gravar
    conversa no lugar errado."""
    dados = request.json or {}
    telefone = str(dados.get("telefone", "")).strip()
    mensagens = dados.get("mensagens") or []

    if not isinstance(mensagens, list):
        return jsonify({"erro": "mensagens deve ser uma lista"}), 400
    if len(mensagens) > MAX_MENSAGENS_POR_INGESTAO:
        mensagens = mensagens[-MAX_MENSAGENS_POR_INGESTAO:]

    _marcar_captura_viva(telefone=normalizar_telefone(telefone))

    canal, lead_ref = _resolver_lead_por_telefone(telefone)
    if not lead_ref:
        return jsonify({"ok": True, "vinculado": False, "novas": 0,
                        "motivo": "nenhum lead com esse telefone"})

    novas = 0
    conexao = db.conectar()
    try:
        total_atual = conexao.execute(
            "SELECT COUNT(*) FROM mensagens_conversa WHERE canal = ? AND lead_ref = ?",
            (canal, str(lead_ref)),
        ).fetchone()[0]

        for bruta in mensagens:
            if not isinstance(bruta, dict):
                continue
            texto = str(bruta.get("texto", "")).strip()[:MAX_CARACTERES_MENSAGEM_CONVERSA]
            autor = str(bruta.get("autor", "")).strip().lower()
            if not texto or autor not in AUTORES_MENSAGEM:
                continue
            if total_atual + novas >= MAX_MENSAGENS_POR_LEAD:
                break

            enviada_em = str(bruta.get("enviada_em") or _agora())
            chave = _chave_dedup(autor, texto, enviada_em, bruta.get("id_externo"))
            try:
                if _inserir_mensagem(conexao, canal, lead_ref, autor, texto, enviada_em, "whatsapp", chave):
                    novas += 1
            except sqlite3.Error:
                logger.exception("falha ao gravar mensagem capturada, seguindo com as demais")

        conexao.commit()
    finally:
        conexao.close()

    if novas:
        logger.info("cockpit: %s mensagem(ns) nova(s) capturada(s) para %s/%s", novas, canal, lead_ref)
    return jsonify({"ok": True, "vinculado": True, "canal": canal,
                    "lead_ref": lead_ref, "novas": novas})
