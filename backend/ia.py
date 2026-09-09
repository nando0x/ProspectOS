"""Integração com os provedores de IA (Gemini, Groq, NVIDIA).

Arquitetura dos prompts:
- Cada geração envia um par (system, user): o SYSTEM carrega a persona do
  copywriter, o perfil do vendedor (configurável) e as regras invariáveis;
  o USER carrega só os dados do lead e as decisões desta rodada.
- Decisões que pedem variação (qual fechamento usar, que horário propor) são
  sorteadas AQUI no servidor e entregues prontas ao modelo - LLM "sorteando"
  colapsa sempre pro mesmo padrão.
- Um único motor de fallback (`executar_com_fallback`) serve todos os usos:
  mensagem do Maps, DM do Instagram e classificação de perfis.
"""

import json
import logging
import random
import time
from datetime import date, datetime, timedelta

import db
from constantes import (
    ESTAGIO_NEGOCIACAO_PADRAO,
    ESTAGIOS_NEGOCIACAO,
    MAX_CARACTERES_ITEM_EVITAR,
    MAX_CARACTERES_JUSTIFICATIVA,
    MAX_CARACTERES_LEITURA_ANALISE,
    MAX_CARACTERES_NICHO_INSTAGRAM,
    MAX_CARACTERES_OBJETIVO_ANALISE,
    MAX_CARACTERES_RESPOSTA_SUGERIDA,
    MAX_CARACTERES_SUGESTAO_DM,
    MAX_ITENS_EVITAR,
    MAX_MENSAGENS_NO_PROMPT,
    PRIORIDADES_VALIDAS,
)

logger = logging.getLogger(__name__)

# Ordem de preferência dos provedores de IA - se o primeiro falhar/estourar cota,
# tenta o próximo automaticamente. Cada usuário pode configurar 1, 2 ou os 3.
ORDEM_PROVEDORES_IA = ["gemini", "groq", "nvidia"]

# Timeout por chamada de IA. Sem ele, um provedor que pendura a conexão travaria
# a geração pra sempre e o fallback nunca chegaria ao próximo provedor.
IA_TIMEOUT_SEGUNDOS = 45

NOMES_AMIGAVEIS_PROVEDOR = {
    "gemini": "Google Gemini",
    "groq": "Groq",
    "nvidia": "NVIDIA Build",
}

# Copy quer criatividade; classificação quer consistência.
TEMPERATURA_COPY = 0.9
TEMPERATURA_CLASSIFICACAO = 0.2

# Evita ficar tentando de novo um provedor que acabou de bater cota - guarda,
# em memória, até quando (time.monotonic()) cada provedor deve ser pulado.
COOLDOWN_COTA_ESTOURADA_SEGUNDOS = 300  # 5 minutos
_provedores_em_cooldown = {}


class NenhumProvedorDisponivel(Exception):
    """Todos os provedores configurados falharam (ou nenhum está configurado).
    `erro_final` carrega o último erro real, ou None se nada chegou a ser tentado."""

    def __init__(self, erro_final):
        super().__init__(str(erro_final))
        self.erro_final = erro_final


def _provedor_em_cooldown(provedor):
    expira_em = _provedores_em_cooldown.get(provedor)
    return expira_em is not None and time.monotonic() < expira_em


def _marcar_cooldown_se_cota(provedor, erro):
    if _e_erro_de_cota(erro):
        _provedores_em_cooldown[provedor] = time.monotonic() + COOLDOWN_COTA_ESTOURADA_SEGUNDOS


def _e_erro_de_cota(erro):
    """Detecta erro de cota/rate-limit olhando primeiro os atributos estruturados
    da exceção (status_code/code do SDK) e o nome da classe, e só por último o
    texto da mensagem - o texto muda entre versões de SDK e idiomas, os códigos não."""
    status = getattr(erro, "status_code", None) or getattr(erro, "code", None)
    if status == 429:
        return True
    if type(erro).__name__ in ("RateLimitError", "ResourceExhausted", "TooManyRequests"):
        return True
    texto = str(erro).lower()
    return (
        "quota" in texto
        or "resource_exhausted" in texto
        or "429" in texto
        or "rate limit" in texto
    )


def traduzir_erro_ia(erro):
    """Converte erros técnicos de qualquer provedor de IA em mensagens que um usuário leigo entende."""
    texto_erro = str(erro).lower()

    if "api_key" in texto_erro or "api key" in texto_erro or isinstance(erro, RuntimeError):
        return str(erro)
    if _e_erro_de_cota(erro):
        return "cota gratuita excedida por agora"
    if "timeout" in texto_erro or "deadline" in texto_erro:
        return "demorou demais para responder"
    if "unavailable" in texto_erro or "503" in texto_erro:
        return "serviço indisponível no momento"

    return "erro inesperado (veja logs/prospeccao.log)"


# ---------------------------------------------------------------------------
# Adapters dos provedores - todos recebem (system, user, temperatura, formato_json)
# ---------------------------------------------------------------------------

def gemini_gerar_mensagem(system, user, temperatura=TEMPERATURA_COPY, formato_json=False):
    from google import genai

    chave = db.obter_config("gemini")
    # google-genai usa timeout em MILISSEGUNDOS no http_options
    cliente = genai.Client(api_key=chave, http_options={"timeout": IA_TIMEOUT_SEGUNDOS * 1000})
    config = {"system_instruction": system, "temperature": temperatura}
    if formato_json:
        config["response_mime_type"] = "application/json"
    resposta = cliente.models.generate_content(
        model="gemini-flash-latest", contents=user, config=config
    )
    return resposta.text.strip()


def groq_gerar_mensagem(system, user, temperatura=TEMPERATURA_COPY, formato_json=False):
    from openai import OpenAI

    chave = db.obter_config("groq")
    cliente = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=chave, timeout=IA_TIMEOUT_SEGUNDOS)
    extras = {"response_format": {"type": "json_object"}} if formato_json else {}
    resposta = cliente.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperatura,
        **extras,
    )
    return resposta.choices[0].message.content.strip()


def nvidia_gerar_mensagem(system, user, temperatura=TEMPERATURA_COPY, formato_json=False):
    from openai import OpenAI

    chave = db.obter_config("nvidia")
    cliente = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=chave, timeout=IA_TIMEOUT_SEGUNDOS)
    extras = {"response_format": {"type": "json_object"}} if formato_json else {}
    resposta = cliente.chat.completions.create(
        model="nvidia/llama-3.3-nemotron-super-49b-v1",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperatura,
        top_p=0.9,
        max_tokens=700,
        **extras,
    )
    return resposta.choices[0].message.content.strip()


GERADORES = {
    "gemini": gemini_gerar_mensagem,
    "groq": groq_gerar_mensagem,
    "nvidia": nvidia_gerar_mensagem,
}


def executar_com_fallback(system, user, parser=None, descricao_log="gerar mensagem",
                          temperatura=TEMPERATURA_COPY, formato_json=False):
    """Tenta o par (system, user) em cada provedor configurado, na ordem de
    preferência. Se um falhar (cota, erro, resposta que o parser rejeita), tenta
    o próximo. Retorna (resultado, provedor_usado, avisos_para_o_usuario);
    levanta NenhumProvedorDisponivel se todos falharem."""
    avisos = []
    erro_final = None

    for provedor in ORDEM_PROVEDORES_IA:
        if not db.obter_config(provedor):
            continue  # provedor não configurado, pula silenciosamente

        if _provedor_em_cooldown(provedor):
            logger.info("provedor %s em cooldown (cota excedida recentemente), pulando", provedor)
            avisos.append(
                f"{NOMES_AMIGAVEIS_PROVEDOR[provedor]} indisponível agora (cota gratuita excedida por agora)."
            )
            continue

        try:
            resposta = GERADORES[provedor](
                system, user, temperatura=temperatura, formato_json=formato_json
            )
            resultado = parser(resposta) if parser else resposta
            logger.info("%s com sucesso via %s", descricao_log, provedor)
            return resultado, provedor, avisos
        except Exception as erro:
            logger.warning("provedor %s falhou ao %s: %s", provedor, descricao_log, erro)
            _marcar_cooldown_se_cota(provedor, erro)
            avisos.append(
                f"{NOMES_AMIGAVEIS_PROVEDOR[provedor]} indisponível agora ({traduzir_erro_ia(erro)})."
            )
            erro_final = erro
            continue

    raise NenhumProvedorDisponivel(erro_final)


# ---------------------------------------------------------------------------
# Blocos compartilhados dos prompts
# ---------------------------------------------------------------------------

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


PERGUNTAS_DE_FECHAMENTO = [
    "Quer que eu te mostre um exemplo rápido?",
    "Faz sentido eu te mandar uma prévia?",
    "Posso te enviar uma ideia de como ficaria?",
    "Quer ver como ficaria o seu?",
    "Posso te mandar um diagnóstico rápido, sem compromisso?",
]

HORARIOS_COMERCIAIS = ["9h", "9h30", "10h", "10h40", "11h", "14h", "14h30", "15h20", "16h", "17h"]
NOMES_DIAS_UTEIS = ["segunda", "terça", "quarta", "quinta", "sexta"]


def sortear_fechamento():
    """Decide AQUI (não no modelo) como a mensagem termina: metade das vezes uma
    pergunta de sim/não, metade uma proposta de horário concreto - com dia útil e
    hora reais gerados agora. Pedir pro LLM 'sortear' faz ele repetir sempre o
    mesmo fechamento e inventar horários fixos."""
    if random.random() < 0.5:
        pergunta = random.choice(PERGUNTAS_DE_FECHAMENTO)
        return (
            f'Encerre com esta pergunta de sim/não (adapte só o necessário para fluir no texto): "{pergunta}"'
        )

    data_alvo = date.today() + timedelta(days=random.randint(1, 3))
    while data_alvo.weekday() >= 5:
        data_alvo += timedelta(days=1)
    dia = NOMES_DIAS_UTEIS[data_alvo.weekday()]
    hora = random.choice(HORARIOS_COMERCIAIS)
    return f"Encerre propondo um horário concreto para uma conversa rápida: {dia} às {hora}."


def _bloco_perfil_vendedor():
    """Perfil configurável de quem envia as mensagens (Configurações → Seu perfil).
    Sem configuração, retorna vazio e o system usa a persona neutra."""
    nome = db.obter_config("vendedor_nome")
    apresentacao = db.obter_config("vendedor_apresentacao")
    diferencial = db.obter_config("vendedor_diferencial")
    if not (nome or apresentacao or diferencial):
        return ""

    linhas = ["", "Quem envia as mensagens (escreva na voz dessa pessoa):"]
    if nome:
        linhas.append(f"- Nome: {nome} (apresente-se pelo nome quando soar natural)")
    if apresentacao:
        linhas.append(f"- O que faz: {apresentacao}")
    if diferencial:
        linhas.append(f"- Diferencial a destacar quando couber: {diferencial}")
    return "\n".join(linhas) + "\n"


def montar_system_copywriter(canal):
    """System prompt fixo do copywriter (canal: 'WhatsApp' ou 'DM do Instagram') +
    o perfil do vendedor quando configurado."""
    tom_canal = (
        "Tom de DM real entre duas pessoas - leve e informal, sem 'prezado(a)', sem formalidade de e-mail."
        if canal == "DM do Instagram"
        else "Tom de conversa direta e confiante entre humanos, sem soar vendedor robótico nem arrogante."
    )

    return f"""Você é um copywriter sênior especializado em prospecção B2B fria via {canal}, com décadas de experiência em vendas consultivas para pequenos negócios locais no Brasil. Donos de empresa recebem spam de "site/marketing" toda semana; suas mensagens se destacam por serem específicas, humanas e fáceis de responder em segundos.
{_bloco_perfil_vendedor()}
Regras invariáveis (valem para TODA mensagem):
- Escreva SEMPRE em primeira pessoa do singular ("eu faço", "ofereço", "posso te mostrar") - quem envia é UMA pessoa que trabalha por conta própria. Nunca "nós", "oferecemos", "nossa equipe" ou qualquer voz de agência.
- {tom_canal}
- Abra de forma natural e direta. Nunca comece com "Estava navegando/pesquisando no Google e vi..." nem variações - é o clichê nº 1 do spam.
- Use APENAS os dados fornecidos; nunca invente números, prêmios, clientes ou depoimentos.
- Adapte o vocabulário ao nicho (clínica → "agenda de pacientes"; imobiliária → "captação de clientes"; restaurante → "reservas e pedidos").
- Se o campo Nome for dominado por nome de pessoa (ex: "Dra. Ana Souza Odontologia"), fale COM a pessoa pelo primeiro nome, "você" no singular. Se for institucional (ex: "Vivarte Odontologia"), use "vocês"/"a equipe", sem inventar nomes.
- Termine com o fechamento EXATO indicado na tarefa - pedido de ação específico e fechado, nunca "faz sentido conversarmos?".
- Responda APENAS com o texto final da mensagem: sem aspas em volta, sem explicações, sem markdown.

Exemplo do tom certo (régua de qualidade - não copie a estrutura literalmente):
"Janete, boa tarde! Vi que a Estética Vit tem nota 5.0 no Google com mais de 100 avaliações - reputação que pouca clínica da região alcança. Só que quem pesquisa 'estética em Cuiabá' fora do Maps não te encontra, e acaba no site de outra clínica. Eu crio sites profissionais para negócios locais; posso te mandar uma prévia de como ficaria o da Vit?"
"""


def _linha_dado(rotulo, valor):
    return f"- {rotulo}: {valor}" if valor not in (None, "", 0) else None


def _bloco_dados_empresa(nome, categoria, endereco, nota, num_avaliacoes=None,
                         cidade=None, instagram_url=None):
    linhas = [
        _linha_dado("Nome", nome),
        _linha_dado("Categoria", categoria or "não informado"),
        _linha_dado("Cidade", cidade),
        _linha_dado("Endereço", endereco or "não informado"),
        _linha_dado("Nota no Google", nota),
        _linha_dado("Número de avaliações no Google", num_avaliacoes),
        _linha_dado("Instagram do negócio", instagram_url),
        _linha_dado("Saudação a usar (hora real de agora)", saudacao_por_horario()),
    ]
    return "\n".join(l for l in linhas if l)


def _contexto_site(site_status, site_problemas):
    if site_status == "site_ruim":
        return (
            f"A empresa TEM um site, mas ele está com problemas sérios detectados automaticamente: "
            f"{site_problemas or 'problemas técnicos'}. A oferta é um site NOVO (reformulação). "
            "Cite o problema de forma LEIGA e respeitosa (ex.: em vez de 'sem viewport', diga que "
            "'o site não abre direito no celular'; em vez de 'HTTP 500', 'o site está fora do ar'), "
            "e use a combinação reputação forte + site problemático como a oportunidade perdida."
        )
    return (
        "A empresa NÃO possui site. Use a combinação reputação forte + ausência de site como a "
        "oportunidade perdida: quem pesquisa no Google fora do Maps não a encontra. Se ela tiver "
        "Instagram, reconheça ('o Instagram de vocês é ativo') e posicione o site como o complemento "
        "que captura quem pesquisa - nunca como substituto da rede social."
    )


# ---------------------------------------------------------------------------
# Copy do Maps (WhatsApp)
# ---------------------------------------------------------------------------

def montar_prompt_contato(nome, categoria, endereco, nota, site_status=None, site_problemas=None,
                          num_avaliacoes=None, cidade=None, instagram_url=None, conteudo_site=None):
    bloco_conteudo = (
        f"""
Conteúdo REAL do site atual da empresa (capturado agora):
\"\"\"{conteudo_site}\"\"\"
Use esse conteúdo para citar UM detalhe específico do site (algo desatualizado, vago ou fraco) em tom respeitoso - isso prova que você realmente olhou o site deles, sem humilhar o trabalho existente.
"""
        if conteudo_site
        else ""
    )

    return f"""Escreva UMA mensagem de primeiro contato via WhatsApp (3-5 frases) oferecendo a criação de um site profissional para a empresa abaixo.

{_contexto_site(site_status, site_problemas)}
{bloco_conteudo}
Dados da empresa:
{_bloco_dados_empresa(nome, categoria, endereco, nota, num_avaliacoes, cidade, instagram_url)}

Orientações desta mensagem:
- Mencione a nota (e o volume de avaliações, se houver) como fato relevante do argumento, não como elogio vazio.
- Encaixe a saudação indicada de forma natural, variando a posição na frase (nem sempre no início).
- {sortear_fechamento()}
"""


def montar_prompt_followup(nome, categoria, endereco, nota, follow_ups_enviados,
                           num_avaliacoes=None, cidade=None, mensagem_anterior=None):
    numero_do_followup = max(follow_ups_enviados, 1)
    if numero_do_followup <= 1:
        orientacao_tom = (
            "Este é o PRIMEIRO follow-up (sem resposta ao primeiro contato). Tom de reforço gentil "
            "e leve, como quem lembra educadamente - a mensagem anterior pode ter passado despercebida."
        )
    else:
        orientacao_tom = (
            f"Este é o follow-up número {numero_do_followup} (já foram {numero_do_followup} mensagens "
            "sem resposta). Seja mais direto e conciso, sem soar impaciente. Traga um elemento NOVO "
            "que não estava nas mensagens anteriores (um prazo, uma prova social genérica sobre ter "
            "site, ou perguntar objetivamente se ainda faz sentido)."
        )

    bloco_anterior = (
        f'\nMensagem já enviada anteriormente (NÃO repita o argumento nem a estrutura dela - varie de verdade):\n"""{mensagem_anterior}"""\n'
        if mensagem_anterior
        else ""
    )

    return f"""Escreva UMA mensagem de FOLLOW-UP via WhatsApp (2-4 frases, mais curta que um primeiro contato) para retomar contato com a empresa abaixo, que recebeu uma proposta de criação de site e não respondeu.

{orientacao_tom}
{bloco_anterior}
Dados da empresa:
{_bloco_dados_empresa(nome, categoria, endereco, nota, num_avaliacoes, cidade)}

Orientações desta mensagem:
- NÃO comece se desculpando por "incomodar de novo" nem com frases inseguras.
- {sortear_fechamento()}
"""


def gerar_mensagem_com_fallback(nome, categoria, endereco, nota, tipo="contato", follow_ups_enviados=0,
                                site_status=None, site_problemas=None, num_avaliacoes=None,
                                cidade=None, instagram_url=None, mensagem_anterior=None,
                                conteudo_site=None):
    """Gera a mensagem de abordagem/follow-up de um lead do Maps.
    Retorna (mensagem, provedor_usado, avisos_para_o_usuario)."""
    if tipo == "followup":
        user = montar_prompt_followup(
            nome, categoria, endereco, nota, follow_ups_enviados,
            num_avaliacoes=num_avaliacoes, cidade=cidade, mensagem_anterior=mensagem_anterior,
        )
    else:
        user = montar_prompt_contato(
            nome, categoria, endereco, nota, site_status, site_problemas,
            num_avaliacoes=num_avaliacoes, cidade=cidade, instagram_url=instagram_url,
            conteudo_site=conteudo_site,
        )

    try:
        return executar_com_fallback(
            montar_system_copywriter("WhatsApp"), user, descricao_log="gerar mensagem"
        )
    except NenhumProvedorDisponivel as excecao:
        if excecao.erro_final is None:
            raise RuntimeError(
                "Nenhuma chave de IA configurada. Crie um arquivo .env com GEMINI_API_KEY, "
                "GROQ_API_KEY e/ou NVIDIA_API_KEY (veja .env.example)."
            )
        raise RuntimeError(
            "Todos os provedores de IA configurados falharam agora. "
            f"Último erro: {traduzir_erro_ia(excecao.erro_final)}"
        )


# ---------------------------------------------------------------------------
# DM do Instagram
# ---------------------------------------------------------------------------

def montar_prompt_contato_instagram(username, full_name, biography, nicho, justificativa):
    linhas = [
        _linha_dado("Username", f"@{username}"),
        _linha_dado("Nome", full_name or "não informado"),
        _linha_dado("Bio", biography or "não informada"),
        _linha_dado("Nicho identificado", nicho or "não identificado"),
        _linha_dado("Por que esse perfil foi priorizado", justificativa),
        _linha_dado("Saudação a usar (hora real de agora)", saudacao_por_horario()),
    ]
    dados = "\n".join(l for l in linhas if l)

    return f"""Escreva UMA mensagem de primeiro contato via DM do Instagram (2-4 frases) oferecendo a criação de um site profissional para o perfil abaixo.

Dados do perfil:
{dados}

Orientações desta mensagem:
- Cite algo específico da bio ou do nicho para mostrar que não é mensagem copiada e colada.
- Não comece com "Oi, tudo bem? Vi seu perfil..." nem variações clichês.
- {sortear_fechamento()}
"""


def montar_prompt_followup_instagram(username, full_name, biography, nicho, follow_ups_enviados,
                                     mensagem_anterior=None):
    numero_do_followup = max(follow_ups_enviados, 1)
    if numero_do_followup <= 1:
        orientacao_tom = (
            "Este é o PRIMEIRO follow-up (sem resposta à primeira DM). Tom de reforço leve e casual - "
            "DMs se perdem fácil no Instagram, assuma isso com naturalidade."
        )
    else:
        orientacao_tom = (
            f"Este é o follow-up número {numero_do_followup}. Seja mais direto e breve, sem soar "
            "insistente. Considere perguntar objetivamente se ainda faz sentido, ou ofereça algo novo."
        )

    bloco_anterior = (
        f'\nDM já enviada anteriormente (NÃO repita o argumento dela - varie de verdade):\n"""{mensagem_anterior}"""\n'
        if mensagem_anterior
        else ""
    )

    linhas = [
        _linha_dado("Username", f"@{username}"),
        _linha_dado("Nome", full_name or "não informado"),
        _linha_dado("Bio", biography or "não informada"),
        _linha_dado("Nicho identificado", nicho or "não identificado"),
        _linha_dado("Saudação a usar (hora real de agora)", saudacao_por_horario()),
    ]
    dados = "\n".join(l for l in linhas if l)

    return f"""Escreva UMA mensagem de FOLLOW-UP via DM do Instagram (1-3 frases, curta e casual) para retomar contato com o perfil abaixo, que recebeu uma DM sobre criação de site e não respondeu.

{orientacao_tom}
{bloco_anterior}
Dados do perfil:
{dados}

Orientações desta mensagem:
- NÃO se desculpe por "incomodar de novo".
- {sortear_fechamento()}
"""


def gerar_mensagem_instagram_com_fallback(username, full_name, biography, nicho, justificativa,
                                          tipo, follow_ups_enviados, mensagem_anterior=None):
    """Gera a DM de abordagem/follow-up de um lead do Instagram.
    Retorna (mensagem, provedor_usado, avisos_para_o_usuario)."""
    if tipo == "followup":
        user = montar_prompt_followup_instagram(
            username, full_name, biography, nicho, follow_ups_enviados,
            mensagem_anterior=mensagem_anterior,
        )
    else:
        user = montar_prompt_contato_instagram(username, full_name, biography, nicho, justificativa)

    try:
        return executar_com_fallback(
            montar_system_copywriter("DM do Instagram"), user,
            descricao_log="gerar mensagem (Instagram)",
        )
    except NenhumProvedorDisponivel as excecao:
        if excecao.erro_final is None:
            raise RuntimeError(
                "Nenhuma chave de IA configurada. Configure em /configuracoes ou no arquivo .env."
            )
        raise RuntimeError(
            f"Todos os provedores de IA configurados falharam agora. Último erro: {traduzir_erro_ia(excecao.erro_final)}"
        )


# ---------------------------------------------------------------------------
# Classificação de perfis do Instagram
# ---------------------------------------------------------------------------

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


SYSTEM_CLASSIFICADOR = """Você é um analista de qualificação de leads de uma operação que vende criação de sites para pequenos negócios locais no Brasil. Você avalia perfis do Instagram que comentaram numa publicação e responde SEMPRE um único objeto JSON válido, sem markdown e sem texto fora do JSON, com EXATAMENTE estas chaves:
- "prioridade": "alta", "media", "baixa" ou "descartado" ("descartado" só sem indício nenhum de negócio/profissional real).
- "nicho": string curta com o nicho/profissão (ex: "advogado", "esteticista"), ou "" se não identificável.
- "justificativa": 1-2 frases explicando a prioridade.
- "sugestao_dm": DM curta e casual (2-4 frases, tom de Instagram, PRIMEIRA PESSOA DO SINGULAR - quem envia é uma pessoa só, freelancer: "eu faço", "ofereço", nunca "nós/oferecemos") - só preencha se prioridade for "alta" ou "media"; senão "".
Bons leads: donos de pequenos negócios locais ou profissionais autônomos, sem site próprio aparente, que se beneficiariam de um site."""


def montar_prompt_classificacao_instagram(perfil, nicho_alvo):
    comentarios = perfil.get("comentarios", [])
    trecho_comentarios = "\n".join(f'- "{c}"' for c in comentarios[:5]) or "(nenhum comentário capturado)"
    contexto_nicho = (
        f'O usuário procura especificamente leads do nicho "{nicho_alvo}". Dê prioridade mais alta a '
        "perfis desse nicho e rebaixe (ou marque 'baixa') os que claramente não pertençam a ele, mesmo "
        "que sejam bons leads de outro tipo."
        if nicho_alvo
        else "O usuário não informou nicho-alvo - avalie de forma geral, priorizando donos de pequenos "
        "negócios locais sem site próprio."
    )

    return f"""{contexto_nicho}

Dados do perfil a avaliar (responda com o JSON especificado):
- Username: @{perfil.get("username")}
- Nome: {perfil.get("full_name") or "não informado"}
- Bio: {perfil.get("biography") or "não informada"}
- Seguidores: {perfil.get("seguidores") or 0}
- Conta comercial: {"sim" if perfil.get("is_business_account") else "não"}
- Comentários feitos no post analisado:
{trecho_comentarios}
"""


def _parsear_classificacao(resposta_bruta):
    resposta_limpa = (
        resposta_bruta.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    )
    dados = json.loads(resposta_limpa)

    prioridade = str(dados.get("prioridade", "")).strip().lower()
    if prioridade not in PRIORIDADES_VALIDAS:
        prioridade = "baixa"

    return {
        "prioridade": prioridade,
        "nicho": str(dados.get("nicho", "")).strip()[:MAX_CARACTERES_NICHO_INSTAGRAM] or None,
        "justificativa": str(dados.get("justificativa", "")).strip()[:MAX_CARACTERES_JUSTIFICATIVA],
        "sugestao_dm": str(dados.get("sugestao_dm", "")).strip()[:MAX_CARACTERES_SUGESTAO_DM],
    }


def classificar_lead_instagram_com_fallback(perfil, nicho_alvo):
    """Classifica um perfil do Instagram (prioridade/nicho/justificativa/sugestão de DM)
    usando o mesmo fallback de provedores das mensagens, com modo JSON nativo dos SDKs
    e temperatura baixa (consistência). Levanta exceção se todos os provedores falharem -
    quem chama deve tratar por perfil, sem abortar o lote inteiro."""
    user = montar_prompt_classificacao_instagram(perfil, nicho_alvo)
    try:
        resultado, _provedor, _avisos = executar_com_fallback(
            SYSTEM_CLASSIFICADOR,
            user,
            parser=_parsear_classificacao,
            descricao_log=f"classificar perfil @{perfil.get('username')}",
            temperatura=TEMPERATURA_CLASSIFICACAO,
            formato_json=True,
        )
        return resultado
    except NenhumProvedorDisponivel as excecao:
        raise RuntimeError(
            f"nenhum provedor de IA conseguiu classificar o perfil (último erro: {excecao.erro_final})"
        )


# ---------------------------------------------------------------------------
# Analista de negociação (cockpit de conversa)
# ---------------------------------------------------------------------------

SYSTEM_ANALISTA_CONVERSA = """Você é um consultor de vendas sênior que acompanha negociações reais por WhatsApp entre um freelancer que cria sites e donos de pequenos negócios locais no Brasil. Você lê a conversa até aqui e orienta o próximo passo.

Responda SEMPRE um único objeto JSON válido, sem markdown e sem texto fora do JSON, com EXATAMENTE estas chaves:
- "estagio": um de "primeiro_contato" (ainda não houve resposta do lead), "descoberta" (respondeu, você ainda está entendendo a situação dele), "interesse" (demonstrou curiosidade ou pediu detalhes), "objecao" (levantou uma barreira: preço, tempo, "já tenho", "não preciso"), "negociacao" (discutindo preço, prazo ou escopo concreto), "fechamento" (perto de fechar, alinhando detalhes finais), "esfriou" (parou de responder ou perdeu o interesse).
- "leitura": 1-3 frases interpretando o que o lead realmente quis dizer e o que isso revela sobre a chance de fechar. Seja específico sobre ESTA conversa, não genérico.
- "objetivo": uma frase curta dizendo qual é o próximo objetivo tático AGORA (ex.: "Entender qual é a real dor dele com o site atual antes de falar de preço").
- "resposta_sugerida": a próxima mensagem pronta para enviar, na voz de quem vende (primeira pessoa do singular). Curta, natural, fácil de responder. Sem saudação repetida se a conversa já está em andamento.
- "evitar": array de 1 a 4 strings curtas com o que NÃO dizer agora (ex.: "Falar de preço antes dele demonstrar interesse"). Cada item é uma frase objetiva.

Princípios de negociação que você aplica:
- Nunca empurre. Quem sente pressão trava. O objetivo de cada mensagem é conseguir a PRÓXIMA resposta, não fechar na hora.
- Objeção não é "não": é pedido de informação. Acolha antes de rebater, e nunca contrarie o lead de frente.
- Se o lead disse que já tem algo (Instagram, site antigo, sobrinho que mexe), valide o que ele já fez e posicione sua solução como complemento, nunca como substituição do que ele escolheu.
- Espelhe o nível de formalidade e o tamanho das mensagens do lead. Se ele escreve curto, você escreve curto.
- Nunca invente dados, preços, prazos, clientes ou resultados que não estejam no contexto fornecido.
- Se o lead ficou em silêncio, o próximo passo é um follow-up leve que dê saída fácil, nunca cobrança."""


def _bloco_historico_conversa(mensagens):
    """Formata o histórico como uma transcrição legível. Só as últimas
    MAX_MENSAGENS_NO_PROMPT entram (conversa longa estoura o contexto e as
    mensagens antigas pesam pouco na decisão do próximo passo)."""
    if not mensagens:
        return "(nenhuma mensagem trocada ainda - o primeiro contato ainda não foi enviado)"

    recentes = mensagens[-MAX_MENSAGENS_NO_PROMPT:]
    omitidas = len(mensagens) - len(recentes)
    linhas = []
    if omitidas > 0:
        linhas.append(f"[... {omitidas} mensagem(ns) mais antiga(s) omitida(s) ...]")
    for mensagem in recentes:
        quem = "VOCÊ (vendedor)" if mensagem["autor"] == "vendedor" else "LEAD"
        quando = (mensagem.get("enviada_em") or "").replace("T", " ")[:16]
        linhas.append(f"[{quando}] {quem}: {mensagem['texto']}")
    return "\n".join(linhas)


def montar_prompt_analise_conversa(lead, mensagens):
    """Monta o prompt do analista: dados do negócio + ângulo de venda (situação
    do site) + transcrição da conversa. Reaproveita os mesmos blocos usados
    pelas copies, para a análise enxergar exatamente o mesmo contexto."""
    dados_empresa = _bloco_dados_empresa(
        lead.get("nome"),
        lead.get("categoria"),
        lead.get("endereco"),
        lead.get("nota"),
        num_avaliacoes=lead.get("num_avaliacoes"),
        cidade=lead.get("cidade"),
        instagram_url=lead.get("instagram_url"),
    )
    contexto_site = _contexto_site(lead.get("site_status"), lead.get("site_problemas"))
    ultima_do_lead = next(
        (m["texto"] for m in reversed(mensagens) if m["autor"] == "lead"), None
    )
    foco = (
        f'\nA última mensagem do lead foi: "{ultima_do_lead}"\nSua resposta sugerida precisa endereçar '
        "exatamente isso.\n"
        if ultima_do_lead
        else "\nO lead ainda não respondeu nenhuma mensagem.\n"
    )

    return f"""Negócio com quem você está negociando:
{dados_empresa}

Contexto da oferta:
{contexto_site}

Conversa até agora (ordem cronológica):
{_bloco_historico_conversa(mensagens)}
{foco}
Saudação correta para a hora de agora, caso precise saudar: {saudacao_por_horario()}

Analise a negociação e responda com o JSON especificado."""


def _parsear_analise_conversa(resposta_bruta):
    resposta_limpa = (
        resposta_bruta.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    )
    dados = json.loads(resposta_limpa)

    estagio = str(dados.get("estagio", "")).strip().lower()
    if estagio not in ESTAGIOS_NEGOCIACAO:
        estagio = ESTAGIO_NEGOCIACAO_PADRAO

    evitar_bruto = dados.get("evitar") or []
    if isinstance(evitar_bruto, str):  # modelo às vezes devolve string única
        evitar_bruto = [evitar_bruto]
    evitar = [
        str(item).strip()[:MAX_CARACTERES_ITEM_EVITAR]
        for item in list(evitar_bruto)[:MAX_ITENS_EVITAR]
        if str(item).strip()
    ]

    return {
        "estagio": estagio,
        "leitura": str(dados.get("leitura", "")).strip()[:MAX_CARACTERES_LEITURA_ANALISE],
        "objetivo": str(dados.get("objetivo", "")).strip()[:MAX_CARACTERES_OBJETIVO_ANALISE],
        "resposta_sugerida": str(dados.get("resposta_sugerida", "")).strip()[:MAX_CARACTERES_RESPOSTA_SUGERIDA],
        "evitar": evitar,
    }


def analisar_conversa_com_fallback(lead, mensagens):
    """Lê o histórico da conversa e devolve (analise, provedor, avisos):
    estágio da negociação, leitura da situação, próximo objetivo, resposta
    sugerida e o que evitar. Mesmo fallback de provedores das copies, com
    modo JSON nativo e temperatura baixa (análise precisa ser consistente)."""
    user = montar_prompt_analise_conversa(lead, mensagens)
    return executar_com_fallback(
        SYSTEM_ANALISTA_CONVERSA,
        user,
        parser=_parsear_analise_conversa,
        descricao_log=f"analisar conversa com {lead.get('nome')}",
        temperatura=TEMPERATURA_CLASSIFICACAO,
        formato_json=True,
    )
