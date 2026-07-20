"""Fonte alternativa de dados do Maps: Google Places API (New).

O usuário escolhe em Configurações → Fonte de dados entre o scraper local
(gosom, padrão) e a API oficial do Google Places. Esta fonte:

- consulta `places:searchText` (paginado, até 60 resultados por busca);
- escreve um CSV com AS MESMAS COLUNAS do CSV bruto do scraper (input_id,
  place_id, title, category, address, review_rating, review_count, phone,
  website) - assim todo o pipeline downstream (linha_qualifica, análise de
  site, dedup por place_id, score) funciona sem nenhuma mudança;
- no modo mapa, usa locationBias circular (o mesmo pino + raio da busca).

A chave fica no cofre de credenciais (config "places", via keyring) e a
cobrança/cota é gerenciada pelo usuário no Google Cloud.
"""

import csv
import logging
import uuid

import requests

logger = logging.getLogger(__name__)

URL_SEARCH_TEXT = "https://places.googleapis.com/v1/places:searchText"
TIMEOUT_SEGUNDOS = 30
RESULTADOS_POR_PAGINA = 20
MAX_PAGINAS_POR_QUERY = 3  # limite da própria API: até 60 resultados por busca

# só os campos que o pipeline consome - field mask menor = requisição mais barata
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.primaryTypeDisplayName",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "nextPageToken",
])

COLUNAS_CSV = [
    "input_id", "place_id", "title", "category", "address",
    "review_rating", "review_count", "phone", "website",
]


class ErroPlacesApi(RuntimeError):
    """Erro da Places API já com mensagem amigável pro usuário."""


def _traduzir_erro_http(resposta):
    if resposta.status_code in (401, 403):
        return (
            "A chave da Google Places API foi recusada. Confira se a chave está certa "
            "e se a 'Places API (New)' está ativada no projeto do Google Cloud."
        )
    if resposta.status_code == 429:
        return (
            "A cota da Google Places API esgotou por agora. Aguarde alguns minutos "
            "ou aumente os limites no Google Cloud."
        )
    detalhe = ""
    try:
        detalhe = resposta.json().get("error", {}).get("message", "")
    except Exception:
        pass
    return f"A Google Places API respondeu com erro {resposta.status_code}. {detalhe}".strip()


def _consultar_pagina(chave, corpo):
    resposta = requests.post(
        URL_SEARCH_TEXT,
        json=corpo,
        headers={
            "X-Goog-Api-Key": chave,
            "X-Goog-FieldMask": FIELD_MASK,
            "Content-Type": "application/json",
        },
        timeout=TIMEOUT_SEGUNDOS,
    )
    if resposta.status_code != 200:
        raise ErroPlacesApi(_traduzir_erro_http(resposta))
    return resposta.json()


def _place_para_linha(place, input_id):
    """Converte um place da API pro formato de linha do CSV bruto do scraper."""
    nota = place.get("rating")
    avaliacoes = place.get("userRatingCount")
    return {
        "input_id": input_id,
        "place_id": place.get("id") or "",
        "title": (place.get("displayName") or {}).get("text") or "",
        "category": (place.get("primaryTypeDisplayName") or {}).get("text") or "",
        "address": place.get("formattedAddress") or "",
        "review_rating": "" if nota is None else str(nota),
        "review_count": "" if avaliacoes is None else str(avaliacoes),
        "phone": place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber") or "",
        "website": place.get("websiteUri") or "",
    }


def _buscar_uma_query(chave, texto_busca, area=None):
    """Busca uma query com paginação. `area` (dict lat/lng/raio_m) liga o
    locationBias circular do modo mapa. Retorna a lista de places."""
    places = []
    token = None
    for _ in range(MAX_PAGINAS_POR_QUERY):
        corpo = {
            "textQuery": texto_busca,
            "languageCode": "pt-BR",
            "regionCode": "BR",
            "pageSize": RESULTADOS_POR_PAGINA,
        }
        if area:
            corpo["locationBias"] = {
                "circle": {
                    "center": {"latitude": area["lat"], "longitude": area["lng"]},
                    # a API aceita raio de até 50000m - mesmo teto do app
                    "radius": min(float(area["raio_m"]), 50000.0),
                }
            }
        if token:
            corpo["pageToken"] = token

        dados = _consultar_pagina(chave, corpo)
        places.extend(dados.get("places") or [])
        token = dados.get("nextPageToken")
        if not token:
            break
    return places


def buscar_com_places_api(queries, arquivo_csv, chave, area=None, callback_query=None):
    """Roda todas as queries na Places API e escreve o CSV bruto (formato do scraper).

    - `queries`: lista de textos de busca, NA MESMA ORDEM do queries.txt - o
      input_id gerado por query preserva o mapeamento query→leads do pipeline.
    - `area`: opcional, dict {lat, lng, raio_m} do modo mapa.
    - `callback_query(indice, total, texto)`: progresso por query.

    Retorna o total de places encontrados. Levanta ErroPlacesApi com mensagem
    amigável em falha de chave/cota/rede.
    """
    total_encontrados = 0
    try:
        with open(arquivo_csv, "w", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_CSV)
            escritor.writeheader()
            for indice, texto in enumerate(queries, start=1):
                if callback_query:
                    callback_query(indice, len(queries), texto)
                input_id = str(uuid.uuid4())
                places = _buscar_uma_query(chave, texto, area=area)
                for place in places:
                    escritor.writerow(_place_para_linha(place, input_id))
                total_encontrados += len(places)
                logger.info("places api: %r retornou %s resultado(s)", texto, len(places))
    except requests.RequestException as erro:
        raise ErroPlacesApi(
            "Não foi possível falar com a Google Places API. Confira sua conexão com a internet."
        ) from erro
    return total_encontrados


def validar_chave_places(chave):
    """Faz uma busca mínima só pra validar a chave. Retorna (ok, mensagem_erro)."""
    try:
        _consultar_pagina(chave, {"textQuery": "padaria em São Paulo", "pageSize": 1, "languageCode": "pt-BR"})
        return True, None
    except ErroPlacesApi as erro:
        return False, str(erro)
    except requests.RequestException:
        return False, "Não foi possível falar com a Google Places API. Confira sua conexão com a internet."
