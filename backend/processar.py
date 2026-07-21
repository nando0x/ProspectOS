"""
Processa o CSV bruto gerado pelo google-maps-scraper:
- filtra empresas com nota >= NOTA_MINIMA e sem site cadastrado
- gera o link do WhatsApp a partir do telefone
- salva tudo num banco local (leads.db) pra nunca repetir o mesmo lead em buscas futuras
- exporta um CSV só com os leads NOVOS de hoje, pronto pra abrir no Excel

Uso:
    py processar.py saidas\bruto.csv [queries.txt]
"""

import csv
import json
import logging
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from paths import DIR_DADOS

logger = logging.getLogger(__name__)

NOTA_MINIMA = 4.0
# tudo que este módulo escreve (saídas, banco, queries.txt da última busca) fica
# na área de dados - na fonte é a pasta do projeto, empacotado é %APPDATA%\ProspectOS
PASTA_SAIDAS = DIR_DADOS / "saidas"
CAMINHO_BANCO = DIR_DADOS / "leads.db"
VERIFICACOES_PARALELAS = 6
CAMINHO_QUERIES_PADRAO = DIR_DADOS / "queries.txt"
LINHAS_POR_COMMIT = 20

# Domínios que NÃO contam como "site próprio da empresa" quando aparecem numa busca
# (redes sociais, marketplaces/agregadores de imóveis, diretórios, órgãos públicos etc.)
DOMINIOS_IGNORADOS = {
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com",
    "olx.com.br", "vivareal.com.br", "zapimoveis.com.br", "imovelweb.com.br",
    "chavesnamao.com.br", "quintoandar.com.br", "nestoria.com.br",
    "empresas.serasaexperian.com.br", "econodata.com.br", "cnpj.biz",
    "google.com", "google.com.br", "maps.google.com",
    "wikipedia.org", "linktr.ee",
}


def dominio_e_proprio(url):
    """True se a URL parece ser o site oficial da própria empresa (não rede social/agregador)."""
    if not url:
        return False

    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False

    host = host.removeprefix("www.")
    if not host:
        return False

    # bate tanto o domínio exato ("facebook.com") quanto qualquer subdomínio dele
    # ("blog.facebook.com", "m.facebook.com") - antes só pegava a igualdade exata
    return not any(host == ignorado or host.endswith("." + ignorado) for ignorado in DOMINIOS_IGNORADOS)


BUSCA_BACKENDS = "duckduckgo,bing,yahoo"
BUSCA_TIMEOUT_SEGUNDOS = 3
SITE_TIMEOUT_SEGUNDOS = 8
USER_AGENT_NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


# Construtores de site genéricos/gratuitos: o site "funciona", mas é modelo
# pronto - comprador clássico de site profissional. Assinaturas por URL final
# e por conteúdo do HTML → nome amigável usado no problema.
CONSTRUTORES_POR_URL = {
    ".wixsite.com": "Wix",
    "sites.google.com": "Google Sites",
    ".negocio.site": "Google Meu Negócio",
    ".webnode.page": "Webnode",
    ".webnode.com.br": "Webnode",
    "canva.site": "Canva",
    ".my.canva.site": "Canva",
    ".wordpress.com": "WordPress.com gratuito",
    ".site123.me": "SITE123",
    ".lojaintegrada.com.br": "Loja Integrada",
    ".comercioplus.com.br": "Comércio Plus",
    ".goomer.app": "Goomer",
}

CONSTRUTORES_POR_HTML = {
    "static.wixstatic.com": "Wix",
    "static.parastorage.com": "Wix",
    'generator" content="wix': "Wix",
    'generator" content="site123': "SITE123",
    'generator" content="webnode': "Webnode",
    "cdn.usite.pro": "uSite",
    "websitebuilder": "construtor de site",
}


def detectar_construtor_generico(url_final, html):
    """Retorna o nome do construtor genérico (Wix, Canva...) ou None."""
    url_minuscula = (url_final or "").lower()
    for assinatura, nome in CONSTRUTORES_POR_URL.items():
        if assinatura in url_minuscula:
            return nome

    html_minusculo = (html or "").lower()
    for assinatura, nome in CONSTRUTORES_POR_HTML.items():
        if assinatura in html_minusculo:
            return nome
    return None


REGEX_RECURSO_HTTP = re.compile(
    r'(?:\ssrc=["\']http://|<link[^>]+href=["\']http://)', re.IGNORECASE
)

# Acima disso, o servidor do site é considerado lento demais (tempo até começar
# a responder - o carregamento completo visto pelo visitante é ainda maior).
LIMITE_RESPOSTA_LENTA_SEGUNDOS = 5


def _e_falha_de_dns(erro):
    """Domínio que não resolve = site provavelmente abandonado/expirado - é
    diferente de servidor fora do ar, e é um gancho de venda mais forte."""
    texto = str(erro).lower()
    return (
        "getaddrinfo" in texto
        or "name or service not known" in texto
        or "nameresolution" in texto
        or "nodename nor servname" in texto
    )


# Itens do raio-X: (nome exibido, função html/url_final → bool "tem")
REGEX_CEP = re.compile(r"\b\d{5}-\d{3}\b")
REGEX_ANO_COPYRIGHT = re.compile(r"(?:©|&copy;|copyright)\D{0,20}(20\d{2})", re.IGNORECASE)


def montar_checklist_site(html, url_final):
    """Raio-X do site com dados reais do HTML: o que o site TEM e o que FALTA
    para transformar visita em contato. Alimenta o modal do lead, o diagnóstico
    em PDF e o prompt da IA - nada aqui é chute, tudo vem da página baixada."""
    html_min = (html or "").lower()

    imagens = len(re.findall(r"<img\b", html_min))
    titulo = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.IGNORECASE | re.DOTALL)
    titulo_texto = re.sub(r"\s+", " ", titulo.group(1)).strip() if titulo else ""
    descricao = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.{30,})["\']',
        html or "", re.IGNORECASE,
    )

    itens = [
        ("botão de WhatsApp", ("wa.me" in html_min or "api.whatsapp.com" in html_min or "whatsapp" in html_min)),
        ("telefone clicável", 'href="tel:' in html_min or "href='tel:" in html_min),
        ("e-mail de contato", "mailto:" in html_min),
        ("link para redes sociais", "instagram.com" in html_min or "facebook.com" in html_min),
        ("endereço ou mapa", ("google.com/maps" in html_min or "maps.google" in html_min
                              or "<address" in html_min or bool(REGEX_CEP.search(html or "")))),
        ("fotos do negócio", imagens >= 3),
        ("título descritivo na aba", len(titulo_texto) > 8 and titulo_texto.lower() not in ("home", "index", "início", "untitled")),
        ("descrição para aparecer no Google", bool(descricao)),
        ("ícone na aba do navegador (favicon)", bool(re.search(r'rel=["\'](?:shortcut )?icon', html_min))),
    ]

    checklist = {
        "tem": [nome for nome, presente in itens if presente],
        "falta": [nome for nome, presente in itens if not presente],
    }

    anos = [int(a) for a in REGEX_ANO_COPYRIGHT.findall(html or "")]
    ano_recente = max(anos) if anos else None
    return checklist, ano_recente


def avaliar_site_completo(url):
    """Avalia a qualidade de um site existente. Retorna (situacao, problemas, checklist):
    situacao 'ok' (site decente - não é lead pra venda de site) ou 'ruim'; checklist
    é o raio-X {tem: [...], falta: [...]} (None quando o site nem abre).

    Checagem de disponibilidade inteligente:
    - falha de DNS = "domínio não encontrado (pode ter expirado)" - definitiva, sem retry;
    - falha de conexão/timeout ganha UMA nova tentativa antes de declarar fora do ar
      (evita falso 'fora do ar' por instabilidade momentânea de rede);
    - URL sem esquema que só responde em HTTP puro vira "sem HTTPS", não "fora do ar".
    Checagens de segurança espelham o navegador: SSL validado, http:// = "não seguro",
    conteúdo misto em página https."""
    import requests
    from requests.exceptions import RequestException, SSLError

    def requisitar(url_alvo, verify=True):
        return requests.get(
            url_alvo,
            timeout=SITE_TIMEOUT_SEGUNDOS,
            headers={"User-Agent": USER_AGENT_NAVEGADOR},
            allow_redirects=True,
            verify=verify,
        )

    def requisitar_com_retentativa(url_alvo, verify=True):
        """Uma nova tentativa em falha transitória; DNS morto falha na hora."""
        try:
            return requisitar(url_alvo, verify)
        except SSLError:
            raise
        except RequestException as erro:
            if _e_falha_de_dns(erro):
                raise
            time.sleep(1)
            return requisitar(url_alvo, verify)

    problemas = []
    dominio_morto = False
    tinha_esquema = url.lower().startswith(("http://", "https://"))
    url_completa = url if tinha_esquema else f"https://{url}"

    resposta = None
    try:
        resposta = requisitar_com_retentativa(url_completa)
    except SSLError:
        problemas.append("certificado de segurança (SSL) inválido ou vencido")
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            resposta = requisitar(url_completa, verify=False)
        except RequestException:
            resposta = None
    except RequestException as erro:
        dominio_morto = _e_falha_de_dns(erro)
        resposta = None

    if resposta is None and not tinha_esquema and not dominio_morto:
        # o servidor pode nem escutar em HTTPS (site antigo, só HTTP): antes de
        # declarar "fora do ar", tenta em HTTP puro - se abrir, o diagnóstico
        # correto é "sem HTTPS" (detectado abaixo pela URL final)
        try:
            resposta = requisitar(f"http://{url}")
        except RequestException:
            resposta = None

    if resposta is None:
        motivo = (
            "domínio não encontrado (pode ter expirado)" if dominio_morto
            else "site fora do ar (não abre)"
        )
        return "ruim", problemas + [motivo], None

    if resposta.status_code >= 400:
        problemas.append(f"site responde com erro (HTTP {resposta.status_code})")

    # site que demora mas "funciona" também é lead: lentidão espanta visitante
    tempo_resposta = getattr(resposta, "elapsed", None)
    if tempo_resposta is not None and tempo_resposta.total_seconds() > LIMITE_RESPOSTA_LENTA_SEGUNDOS:
        problemas.append(
            f"site muito lento para responder ({tempo_resposta.total_seconds():.0f}s)"
        )

    html = (resposta.text or "")[:200_000]
    url_final = resposta.url.lower()

    if url_final.startswith("http://"):
        problemas.append("sem HTTPS (aparece como 'não seguro' no navegador)")
    elif url_final.startswith("https://") and REGEX_RECURSO_HTTP.search(html):
        problemas.append("página segura carregando itens inseguros (conteúdo misto)")

    if "viewport" not in html.lower():
        problemas.append("não adaptado para celular")
    if len(html.strip()) < 800:
        problemas.append("página quase vazia")

    construtor = detectar_construtor_generico(resposta.url, html)
    if construtor:
        problemas.append(f"feito em construtor pronto ({construtor})")

    checklist, ano_copyright = montar_checklist_site(html, url_final)

    ano_atual = date.today().year
    if ano_copyright and ano_copyright <= ano_atual - 2:
        problemas.append(f"sem sinal de atualização desde {ano_copyright}")

    return ("ruim", problemas, checklist) if problemas else ("ok", [], checklist)


def avaliar_site(url):
    """Compatibilidade: mesma avaliação, sem o checklist. Use avaliar_site_completo
    quando o raio-X (tem/falta) for necessário."""
    situacao, problemas, _checklist = avaliar_site_completo(url)
    return situacao, problemas


MAX_CHARS_TEXTO_SITE = 1200


def capturar_conteudo_site(url):
    """Extrai o conteúdo visível do site do lead (título, description, h1/h2 e um
    trecho do texto) para a IA citar detalhes reais na copy e para o diagnóstico.
    Best-effort: qualquer falha retorna None, nunca trava a geração."""
    import requests
    from requests.exceptions import RequestException

    url_completa = url if url.lower().startswith(("http://", "https://")) else f"https://{url}"
    try:
        resposta = requests.get(
            url_completa,
            timeout=SITE_TIMEOUT_SEGUNDOS,
            headers={"User-Agent": USER_AGENT_NAVEGADOR},
            allow_redirects=True,
        )
    except RequestException:
        return None
    if resposta.status_code >= 400:
        return None

    html = (resposta.text or "")[:300_000]

    def _primeiro(padrao):
        encontrado = re.search(padrao, html, re.IGNORECASE | re.DOTALL)
        return re.sub(r"\s+", " ", encontrado.group(1)).strip() if encontrado else None

    titulo = _primeiro(r"<title[^>]*>(.*?)</title>")
    descricao = _primeiro(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']'
    ) or _primeiro(r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']')

    cabecalhos = [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()
        for h in re.findall(r"<h[12][^>]*>(.*?)</h[12]>", html, re.IGNORECASE | re.DOTALL)
    ][:6]

    corpo = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    corpo = re.sub(r"<[^>]+>", " ", corpo)
    corpo = re.sub(r"\s+", " ", corpo).strip()[:MAX_CHARS_TEXTO_SITE]

    if not (titulo or descricao or cabecalhos or corpo):
        return None

    partes = []
    if titulo:
        partes.append(f"Título da página: {titulo}")
    if descricao:
        partes.append(f"Descrição (meta): {descricao}")
    if cabecalhos:
        partes.append("Cabeçalhos: " + " | ".join(c for c in cabecalhos if c))
    if corpo:
        partes.append(f"Trecho do texto visível: {corpo}")
    return "\n".join(partes)


REGEX_PERFIL_INSTAGRAM = re.compile(
    r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)/?$"
)
PATHS_INSTAGRAM_QUE_NAO_SAO_PERFIL = {"p", "reel", "reels", "tv", "explore", "accounts", "stories"}


def buscar_instagram_da_empresa(nome, cidade_ou_endereco=""):
    """Tenta achar o perfil de Instagram do negócio numa busca web - abre um
    segundo canal de abordagem quando o WhatsApp não responde. Best-effort:
    qualquer falha vira None, nunca trava o processamento."""
    try:
        from ddgs import DDGS
    except ImportError:
        return None

    consulta = f"{nome} {cidade_ou_endereco} instagram".strip()
    try:
        resultados = DDGS(timeout=BUSCA_TIMEOUT_SEGUNDOS).text(
            consulta, max_results=5, region="br-pt", backend=BUSCA_BACKENDS
        )
    except Exception:
        return None

    for resultado in resultados:
        url = (resultado.get("href") or "").split("?")[0]
        correspondencia = REGEX_PERFIL_INSTAGRAM.match(url)
        if correspondencia:
            username = correspondencia.group(1)
            if username.lower() not in PATHS_INSTAGRAM_QUE_NAO_SAO_PERFIL:
                return f"https://www.instagram.com/{username}/"
    return None


def buscar_site_da_empresa(nome, cidade_ou_endereco=""):
    """
    Busca se a empresa já tem site próprio (mesmo que o Google Maps não tenha esse
    campo preenchido). Retorna a URL encontrada, ou None se não achar nenhum site
    que pareça ser da própria empresa.

    Usa backend fixo (duckduckgo,bing,yahoo) em vez do padrão "auto" da lib ddgs,
    que tenta até 9 provedores diferentes (Wikipedia, Grokipedia, Mojeek, Google,
    Brave, Startpage...) e deixava cada verificação levar 5-15s. Com poucos
    backends rápidos e um timeout curto, cada verificação cai pra ~1-2s.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        return None

    consulta = f"{nome} {cidade_ou_endereco} site oficial".strip()

    try:
        resultados = DDGS(timeout=BUSCA_TIMEOUT_SEGUNDOS).text(
            consulta, max_results=5, region="br-pt", backend=BUSCA_BACKENDS
        )
    except Exception:
        return None  # falha na busca não deve travar o processamento do lead

    for resultado in resultados:
        url = resultado.get("href")
        if url and dominio_e_proprio(url):
            return url

    return None

# DDDs que precisam do "9" extra na frente do número local (regra do WhatsApp/E.164 para o Brasil)
DDDS_COM_NOVE = {"11", "12", "13", "14", "15", "16", "17", "18", "19", "21", "22", "24", "27", "28"}


def preparar_banco(conexao):
    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            place_id TEXT PRIMARY KEY,
            nome TEXT,
            categoria TEXT,
            endereco TEXT,
            nota REAL,
            num_avaliacoes INTEGER,
            whatsapp_link TEXT,
            telefone TEXT,
            query_origem TEXT,
            status TEXT DEFAULT 'novo',
            observacoes TEXT,
            mensagem_gerada TEXT,
            visto_em TEXT,
            atualizado_em TEXT
        )
        """
    )
    conexao.commit()
    migrar_banco(conexao)


def migrar_banco(conexao):
    """Migrações aditivas do schema - roda toda vez que o banco é aberto, é seguro
    rodar múltiplas vezes (idempotente). Nunca recria/apaga tabelas ou dados existentes."""
    # usa índice numérico (não depende do row_factory configurado na conexão do chamador)
    colunas_existentes = {linha[1] for linha in conexao.execute("PRAGMA table_info(leads)")}

    novas_colunas = {
        "tags": "TEXT",
        "proximo_followup": "TEXT",
        "nicho": "TEXT",
        "cidade": "TEXT",
        "follow_ups_enviados": "INTEGER NOT NULL DEFAULT 0",
        "ultimo_followup_em": "TEXT",
        "site_url": "TEXT",
        "site_status": "TEXT",  # 'sem_site' | 'site_ruim'
        "site_problemas": "TEXT",
        "site_checklist": "TEXT",  # JSON {"tem": [...], "falta": [...]} - raio-X do site
        "instagram_url": "TEXT",
    }
    for nome, tipo in novas_colunas.items():
        if nome not in colunas_existentes:
            conexao.execute(f"ALTER TABLE leads ADD COLUMN {nome} {tipo}")

    # Backfill: todos os leads anteriores a esta coluna entraram pelo filtro
    # antigo, que só aceitava empresa sem site.
    conexao.execute("UPDATE leads SET site_status = 'sem_site' WHERE site_status IS NULL")

    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS historico_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            place_id TEXT NOT NULL,
            status_anterior TEXT,
            status_novo TEXT NOT NULL,
            alterado_em TEXT NOT NULL
        )
        """
    )

    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS instagram_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_url TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            etapa TEXT NOT NULL DEFAULT 'pendente',
            total_comentarios INTEGER,
            total_perfis INTEGER,
            erro_mensagem TEXT
        )
        """
    )

    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS instagram_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL REFERENCES instagram_posts(id),
            username TEXT NOT NULL,
            full_name TEXT,
            is_private INTEGER,
            biography TEXT,
            seguidores INTEGER,
            is_business_account INTEGER,
            comentarios TEXT,
            prioridade TEXT,
            justificativa TEXT,
            sugestao_dm TEXT,
            atualizado_em TEXT
        )
        """
    )

    colunas_instagram_leads = {
        linha[1] for linha in conexao.execute("PRAGMA table_info(instagram_leads)")
    }
    novas_colunas_instagram_leads = {
        "status": "TEXT DEFAULT 'novo'",
        "nicho": "TEXT",
        "observacoes": "TEXT",
        "tags": "TEXT",
        "proximo_followup": "TEXT",
        "follow_ups_enviados": "INTEGER NOT NULL DEFAULT 0",
        "ultimo_followup_em": "TEXT",
    }
    for nome, tipo in novas_colunas_instagram_leads.items():
        if nome not in colunas_instagram_leads:
            conexao.execute(f"ALTER TABLE instagram_leads ADD COLUMN {nome} {tipo}")

    colunas_instagram_posts = {
        linha[1] for linha in conexao.execute("PRAGMA table_info(instagram_posts)")
    }
    if "nicho_alvo" not in colunas_instagram_posts:
        conexao.execute("ALTER TABLE instagram_posts ADD COLUMN nicho_alvo TEXT")
    if "arquivado_em" not in colunas_instagram_posts:
        conexao.execute("ALTER TABLE instagram_posts ADD COLUMN arquivado_em TEXT")
    if "arquivo_comentarios" not in colunas_instagram_posts:
        # caminho do JSON de comentários já raspado - permite retomar uma análise
        # interrompida sem raspar o post de novo (menos risco pra conta)
        conexao.execute("ALTER TABLE instagram_posts ADD COLUMN arquivo_comentarios TEXT")

    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS historico_status_instagram (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            status_anterior TEXT,
            status_novo TEXT NOT NULL,
            alterado_em TEXT NOT NULL
        )
        """
    )

    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS templates_mensagem (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            texto TEXT NOT NULL,
            nicho TEXT,
            vezes_usado INTEGER NOT NULL DEFAULT 0,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        )
        """
    )

    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT,
            atualizado_em TEXT
        )
        """
    )

    # Registro persistente dos jobs de background (busca no Maps / análise de
    # post do Instagram). O estado "vivo" continua em memória; esta tabela é o
    # histórico que sobrevive a restarts - jobs 'rodando' órfãos são marcados
    # como 'interrompido' no startup do app.
    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'rodando',
            etapa TEXT,
            mensagem TEXT,
            progresso_atual INTEGER NOT NULL DEFAULT 0,
            progresso_total INTEGER NOT NULL DEFAULT 0,
            referencia_id INTEGER,
            iniciado_em TEXT NOT NULL,
            atualizado_em TEXT,
            finalizado_em TEXT
        )
        """
    )
    conexao.commit()

    _criar_indices(conexao)
    _preencher_nicho_e_cidade_faltantes(conexao)
    _deduplicar_leads_instagram_por_username(conexao)


# Índices nas colunas mais filtradas/ordenadas. Imperceptível com poucos leads,
# mas evita full-table-scan conforme o banco cresce. Idempotente (roda todo boot).
_INDICES = [
    "CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)",
    "CREATE INDEX IF NOT EXISTS idx_leads_proximo_followup ON leads(proximo_followup)",
    "CREATE INDEX IF NOT EXISTS idx_leads_nicho ON leads(nicho)",
    "CREATE INDEX IF NOT EXISTS idx_leads_site_status ON leads(site_status)",
    "CREATE INDEX IF NOT EXISTS idx_leads_visto_em ON leads(visto_em)",
    "CREATE INDEX IF NOT EXISTS idx_ig_leads_post_id ON instagram_leads(post_id)",
    "CREATE INDEX IF NOT EXISTS idx_ig_leads_status ON instagram_leads(status)",
    "CREATE INDEX IF NOT EXISTS idx_ig_leads_proximo_followup ON instagram_leads(proximo_followup)",
    "CREATE INDEX IF NOT EXISTS idx_hist_status ON historico_status(alterado_em, status_novo)",
    "CREATE INDEX IF NOT EXISTS idx_hist_status_ig ON historico_status_instagram(alterado_em, status_novo)",
]


def _criar_indices(conexao):
    for sql in _INDICES:
        conexao.execute(sql)
    conexao.commit()


def _deduplicar_leads_instagram_por_username(conexao):
    """A mesma pessoa pode comentar em vários posts analisados. Cada lead do
    Instagram passa a existir uma única vez (por username): esta migração remove
    duplicatas antigas e cria o índice único que o upsert da análise usa.
    Entre duplicatas, mantém a linha mais "avançada": primeiro quem já saiu do
    status 'novo' (progresso feito pelo usuário), depois a atualizada mais
    recentemente."""
    conexao.execute(
        """
        DELETE FROM instagram_leads WHERE id NOT IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY username
                    ORDER BY CASE WHEN status IS NOT NULL AND status != 'novo' THEN 0 ELSE 1 END,
                             atualizado_em DESC, id DESC
                ) AS posicao
                FROM instagram_leads
            ) WHERE posicao = 1
        )
        """
    )
    conexao.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_instagram_leads_username ON instagram_leads(username)"
    )
    conexao.commit()


def extrair_nicho_e_cidade(query_origem):
    """Separa uma query de busca ("clínica de estética em Londrina") em nicho
    ("clínica de estética") e cidade ("Londrina"). Usa a ÚLTIMA ocorrência de
    " em " como separador (mais seguro que a primeira, caso o nome do nicho
    contenha "em" no meio). Se não achar o padrão, devolve a query inteira como
    nicho e cidade vazia - nunca perde informação."""
    texto = (query_origem or "").strip()
    if not texto:
        return "", ""

    indice = texto.rfind(" em ")
    if indice == -1:
        return texto, ""

    nicho = texto[:indice].strip()
    cidade = texto[indice + len(" em "):].strip()
    return nicho, cidade


def _preencher_nicho_e_cidade_faltantes(conexao):
    """Backfill: para leads antigos que só têm query_origem preenchido (antes das
    colunas nicho/cidade existirem), extrai e preenche as duas colunas novas."""
    linhas = conexao.execute(
        "SELECT place_id, query_origem FROM leads WHERE (nicho IS NULL OR nicho = '') AND query_origem != ''"
    ).fetchall()
    for place_id, query_origem in linhas:
        nicho, cidade = extrair_nicho_e_cidade(query_origem)
        conexao.execute(
            "UPDATE leads SET nicho = ?, cidade = ? WHERE place_id = ?",
            (nicho, cidade, place_id),
        )
    if linhas:
        conexao.commit()


def telefone_limpo(telefone_bruto):
    """Só os dígitos do telefone, sem formatação - pra exibir/copiar na interface."""
    return re.sub(r"\D", "", telefone_bruto or "") or None


def mapear_queries_por_input_id(caminho_csv_bruto, caminho_queries):
    """
    O scraper não grava o texto da query no CSV, só um 'input_id' (um UUID por busca).
    Como cada busca do queries.txt vira exatamente um input_id, associamos pela ordem
    de aparição no CSV com a ordem das linhas do queries.txt.
    """
    if not caminho_queries or not Path(caminho_queries).exists():
        return {}

    with open(caminho_queries, encoding="utf-8") as arquivo:
        queries = [linha.strip() for linha in arquivo if linha.strip()]

    ids_em_ordem = []
    with open(caminho_csv_bruto, encoding="utf-8") as arquivo:
        for linha in csv.DictReader(arquivo):
            input_id = linha.get("input_id")
            if input_id and input_id not in ids_em_ordem:
                ids_em_ordem.append(input_id)

    return dict(zip(ids_em_ordem, queries))


def telefone_para_whatsapp(telefone_bruto):
    """Converte um telefone brasileiro (como vem do Google Maps) num link wa.me. Retorna None se não der pra usar."""
    digitos = re.sub(r"\D", "", telefone_bruto or "")

    if not digitos:
        return None

    # remove o "0" de discagem interurbana, se vier na frente (ex: 0xx41...)
    if digitos.startswith("0"):
        digitos = digitos[1:]

    # remove o DDI 55 se já vier incluso, pra normalizar sempre a partir do DDD
    if digitos.startswith("55") and len(digitos) > 11:
        digitos = digitos[2:]

    if len(digitos) not in (10, 11):
        return None  # não parece um telefone brasileiro válido (DDD + número)

    ddd = digitos[:2]
    numero = digitos[2:]

    # celular sem o "9" na frente, em DDD que exige o "9" -> adiciona
    if len(numero) == 8 and ddd in DDDS_COM_NOVE:
        numero = "9" + numero

    return f"https://wa.me/55{ddd}{numero}"


def linha_qualifica(linha):
    """Filtro rápido (sem rede): só a nota mínima. Ter site NÃO desqualifica mais
    aqui - a qualidade do site é avaliada depois (site ruim também é lead)."""
    nota_bruta = (linha.get("review_rating") or "").strip()
    if not nota_bruta:
        return False

    try:
        nota = float(nota_bruta.replace(",", "."))
    except ValueError:
        return False

    return nota >= NOTA_MINIMA


def numero_seguro(valor_bruto, conversor, padrao=0):
    """Converte um valor de texto pra número, sem levantar exceção em formatos inesperados
    (ex: '1.234' com ponto de milhar, ou lixo não numérico vindo de uma mudança no scraper)."""
    texto = (valor_bruto or "").strip()
    if not texto:
        return padrao
    try:
        return conversor(texto.replace(",", "."))
    except ValueError:
        try:
            # tenta remover separadores de milhar antes de desistir
            return conversor(re.sub(r"[^\d.]", "", texto))
        except ValueError:
            logger.warning("valor numérico inesperado, usando padrão: %r", valor_bruto)
            return padrao


def _verificar_candidata(indice, linha):
    """Roda numa thread do pool: só a parte de rede, sem tocar no banco.
    1. descobre o site (campo do Maps, ou busca web se o Maps não tiver);
    2. se houver site, avalia a qualidade dele (ok = descarta; ruim = lead de redesign);
    3. se for lead (sem site ou site ruim), tenta achar o Instagram do negócio."""
    nome_empresa = linha.get("title") or ""
    endereco = linha.get("address") or ""

    site_url = (linha.get("website") or "").strip() or buscar_site_da_empresa(nome_empresa, endereco)

    if site_url:
        situacao, problemas, checklist = avaliar_site_completo(site_url)
    else:
        situacao, problemas, checklist = "sem_site", [], None

    instagram_url = buscar_instagram_da_empresa(nome_empresa, endereco) if situacao != "ok" else None

    return indice, linha, {
        "site_url": site_url or None,
        "situacao": situacao,  # "sem_site" | "ruim" | "ok"
        "problemas": problemas,
        "checklist": checklist,
        "instagram_url": instagram_url,
    }


def processar(caminho_csv_bruto, caminho_queries=CAMINHO_QUERIES_PADRAO, callback_progresso=None,
              cidade_padrao=None, sufixo_saida=""):
    """Processa o CSV bruto do scraper. `cidade_padrao` preenche a cidade quando a
    query não tem " em <cidade>" (busca por mapa: a query é só o nicho, e a cidade
    vem do pino). `sufixo_saida` diferencia o CSV de novos quando várias áreas são
    processadas na mesma rodada (senão uma sobrescreveria a outra)."""
    caminho_csv_bruto = Path(caminho_csv_bruto)
    PASTA_SAIDAS.mkdir(exist_ok=True)

    hoje = date.today().isoformat()
    agora = datetime.now().isoformat(timespec="seconds")
    queries_por_input_id = mapear_queries_por_input_id(caminho_csv_bruto, caminho_queries)
    novos = []
    descartados_por_site_ok = 0
    novos_sem_site = 0
    novos_site_ruim = 0
    erros_de_linha = 0
    total_no_csv = 0
    # contadores do funil: cada motivo de descarte é contado pra mensagem final
    # explicar POR QUE "o Google mostrava 20 e só virou 2" - sem isso o usuário
    # acha que a busca está bugada quando na verdade é o filtro fazendo o papel dele
    descartados_nota_baixa = 0
    descartados_sem_telefone = 0

    # Fase 1: filtra candidatas (rápido, sem rede) e prepara link do WhatsApp de cada uma
    candidatas = []
    with open(caminho_csv_bruto, encoding="utf-8") as arquivo:
        for linha in csv.DictReader(arquivo):
            total_no_csv += 1
            if not linha_qualifica(linha):
                descartados_nota_baixa += 1  # nota < mínima ou sem avaliação
                continue
            link_whatsapp = telefone_para_whatsapp(linha.get("phone"))
            if not link_whatsapp:
                descartados_sem_telefone += 1
                continue
            candidatas.append((linha, link_whatsapp))

    total_candidatas = len(candidatas)
    processadas = 0

    # Fase 2: verifica se cada candidata já tem site real, em paralelo (é tudo espera de
    # rede, então rodar várias ao mesmo tempo reduz muito o tempo total desta etapa)
    resultados_verificacao = {}
    with ThreadPoolExecutor(max_workers=VERIFICACOES_PARALELAS) as executor:
        futuros = [
            executor.submit(_verificar_candidata, indice, linha)
            for indice, (linha, _) in enumerate(candidatas)
        ]
        for futuro in as_completed(futuros):
            indice, linha, site_real_encontrado = futuro.result()
            resultados_verificacao[indice] = site_real_encontrado
            processadas += 1
            if callback_progresso:
                callback_progresso(processadas, total_candidatas, linha.get("title") or "")

    # Fase 3: grava no banco sequencialmente (evita concorrência de escrita no SQLite)
    conexao = sqlite3.connect(CAMINHO_BANCO, timeout=10)
    conexao.execute("PRAGMA journal_mode=WAL")
    conexao.execute("PRAGMA busy_timeout=10000")
    conexao.execute("PRAGMA foreign_keys=ON")
    preparar_banco(conexao)

    linhas_desde_commit = 0
    try:
        for indice, (linha, link_whatsapp) in enumerate(candidatas):
            try:
                verificacao = resultados_verificacao.get(indice) or {
                    "site_url": None, "situacao": "sem_site", "problemas": [],
                    "checklist": None, "instagram_url": None,
                }
                if verificacao["situacao"] == "ok":
                    descartados_por_site_ok += 1
                    continue  # site decente: não é lead pra venda de site

                site_status = "sem_site" if verificacao["situacao"] == "sem_site" else "site_ruim"
                site_problemas = "; ".join(verificacao["problemas"]) or None
                site_checklist = (
                    json.dumps(verificacao.get("checklist"), ensure_ascii=False)
                    if verificacao.get("checklist") else None
                )

                place_id = linha.get("place_id") or linha.get("input_id")
                nota = numero_seguro(linha.get("review_rating"), float, padrao=0.0)
                num_avaliacoes = numero_seguro(linha.get("review_count"), lambda t: int(float(t)), padrao=0)
                query_origem = queries_por_input_id.get(linha.get("input_id"), "")
                nicho, cidade = extrair_nicho_e_cidade(query_origem)
                if not cidade and cidade_padrao:
                    cidade = cidade_padrao

                ja_existia = conexao.execute(
                    "SELECT 1 FROM leads WHERE place_id = ?", (place_id,)
                ).fetchone()

                # Sempre atualiza os campos "vivos" do Maps (podem ter mudado desde a
                # última captura), mas nunca mexe em status/tags/observações/mensagem_gerada/
                # proximo_followup - esses são dados que o usuário preencheu manualmente.
                conexao.execute(
                    """
                    INSERT INTO leads (
                        place_id, nome, categoria, endereco, nota, num_avaliacoes,
                        whatsapp_link, telefone, query_origem, nicho, cidade,
                        site_url, site_status, site_problemas, site_checklist, instagram_url,
                        visto_em, atualizado_em
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(place_id) DO UPDATE SET
                        nome = excluded.nome,
                        categoria = excluded.categoria,
                        endereco = excluded.endereco,
                        nota = excluded.nota,
                        num_avaliacoes = excluded.num_avaliacoes,
                        whatsapp_link = excluded.whatsapp_link,
                        telefone = excluded.telefone,
                        site_url = excluded.site_url,
                        site_status = excluded.site_status,
                        site_problemas = excluded.site_problemas,
                        site_checklist = excluded.site_checklist,
                        instagram_url = COALESCE(excluded.instagram_url, instagram_url),
                        atualizado_em = excluded.atualizado_em
                    """,
                    (
                        place_id,
                        linha.get("title"),
                        linha.get("category"),
                        linha.get("address"),
                        nota,
                        num_avaliacoes,
                        link_whatsapp,
                        telefone_limpo(linha.get("phone")),
                        query_origem,
                        nicho,
                        cidade,
                        verificacao["site_url"],
                        site_status,
                        site_problemas,
                        site_checklist,
                        verificacao["instagram_url"],
                        hoje,
                        agora,
                    ),
                )

                if not ja_existia:  # só é "novo" se realmente não existia antes
                    if site_status == "sem_site":
                        novos_sem_site += 1
                    else:
                        novos_site_ruim += 1
                    novos.append(
                        {
                            "nome": linha.get("title"),
                            "categoria": linha.get("category"),
                            "endereco": linha.get("address"),
                            "nota": nota,
                            "num_avaliacoes": num_avaliacoes,
                            "whatsapp": link_whatsapp,
                            "situacao_site": "sem site" if site_status == "sem_site" else f"site ruim ({site_problemas})",
                            "instagram": verificacao["instagram_url"] or "",
                        }
                    )

                linhas_desde_commit += 1
                if linhas_desde_commit >= LINHAS_POR_COMMIT:
                    conexao.commit()
                    linhas_desde_commit = 0

            except Exception:
                erros_de_linha += 1
                logger.exception("erro ao processar uma linha do CSV bruto, pulando essa linha")
                continue
    finally:
        conexao.commit()  # commit final, cobre o que não bateu o múltiplo de LINHAS_POR_COMMIT
        conexao.close()

    caminho_saida = PASTA_SAIDAS / f"leads_novos_{hoje}{sufixo_saida}.csv"
    with open(caminho_saida, "w", newline="", encoding="utf-8-sig") as arquivo:
        campos = ["nome", "categoria", "endereco", "nota", "num_avaliacoes", "whatsapp", "situacao_site", "instagram"]
        escritor = csv.DictWriter(arquivo, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(novos)

    print(f"Leads novos encontrados nesta rodada: {len(novos)} ({novos_sem_site} sem site, {novos_site_ruim} com site ruim)")
    if descartados_por_site_ok:
        print(f"Descartados por já terem um site decente: {descartados_por_site_ok}")
    if erros_de_linha:
        print(f"Atenção: {erros_de_linha} linha(s) do CSV tiveram erro e foram puladas (veja logs/prospeccao.log).")
    print(f"Planilha gerada: {caminho_saida}")

    return {
        "total_no_csv": total_no_csv,
        "novos": len(novos),
        "novos_sem_site": novos_sem_site,
        "novos_site_ruim": novos_site_ruim,
        "descartados_por_site_ok": descartados_por_site_ok,
        "descartados_nota_baixa": descartados_nota_baixa,
        "descartados_sem_telefone": descartados_sem_telefone,
        "erros_de_linha": erros_de_linha,
    }


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("Uso: py processar.py <caminho_do_csv_bruto> [caminho_queries.txt]")
        sys.exit(1)

    if len(sys.argv) == 3:
        processar(sys.argv[1], sys.argv[2])
    else:
        processar(sys.argv[1])
