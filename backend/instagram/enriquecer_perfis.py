"""
Enriquece o JSON de comentários com dados de perfil (público/privado, bio,
seguidores) de cada autor único que comentou.

Uso:
    py enriquecer_perfis.py <caminho_do_json_de_comentarios>

Requer sessão salva previamente com:
    py login.py <seu_usuario>

Aviso: este passo é mais arriscado para a conta que a extração de
comentários, pois faz 1 requisição extra por autor único. Use com
moderação (ex.: só para os comentários que você já pré-selecionou).
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import ClientError, LoginRequired, UserNotFound

PASTA_SESSAO = Path(__file__).parent / "sessao"
DELAY_ENTRE_PERFIS = 8  # segundos, entre cada consulta de perfil


def carregar_sessao() -> Client:
    arquivos_sessao = list(PASTA_SESSAO.glob("session-*.json"))
    if not arquivos_sessao:
        raise RuntimeError(
            "Nenhuma sessão salva encontrada em instagram/sessao/. "
            "Rode primeiro: py login.py <seu_usuario>"
        )
    cliente = Client()
    cliente.load_settings(arquivos_sessao[0])
    return cliente


def agrupar_comentarios_por_usuario(comentarios: list[dict]) -> dict:
    agrupado = {}
    for comentario in comentarios:
        username = comentario["username"]
        agrupado.setdefault(username, []).append(comentario["texto"])
    return agrupado


def enriquecer_perfis(caminho_json: Path, callback_progresso=None) -> Path:
    dados = json.loads(caminho_json.read_text(encoding="utf-8"))
    comentarios_por_usuario = agrupar_comentarios_por_usuario(dados["comentarios"])

    cliente = carregar_sessao()

    perfis = []
    total = len(comentarios_por_usuario)
    for i, (username, textos) in enumerate(comentarios_por_usuario.items(), start=1):
        print(f"[{i}/{total}] Consultando perfil @{username}...")
        if callback_progresso:
            callback_progresso(i, total, username)
        item = {
            "username": username,
            "comentarios": textos,
        }
        try:
            perfil = cliente.user_info_by_username(username)
            item.update({
                "is_private": perfil.is_private,
                "full_name": perfil.full_name,
                "biography": perfil.biography,
                "seguidores": perfil.follower_count,
                "is_business_account": perfil.is_business,
                "external_url": perfil.external_url,
            })
        except UserNotFound:
            item["erro"] = "perfil não encontrado (pode ter sido removido ou renomeado)"
        except LoginRequired:
            item["erro"] = "sessão expirada ao consultar este perfil"
        except ClientError as erro:
            item["erro"] = f"perfil inacessível (rate limit ou outro erro): {erro}"

        perfis.append(item)

        if i < total:
            time.sleep(DELAY_ENTRE_PERFIS)

    resultado = {
        "post_url": dados.get("post_url"),
        "enriquecido_em": datetime.now().isoformat(timespec="seconds"),
        "perfis": perfis,
    }

    caminho_saida = caminho_json.with_name(
        caminho_json.stem + "_enriquecido.json"
    )
    caminho_saida.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return caminho_saida


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: py enriquecer_perfis.py <caminho_do_json_de_comentarios>")
        sys.exit(1)

    caminho_json = Path(sys.argv[1])
    if not caminho_json.exists():
        print(f"Erro: arquivo não encontrado: {caminho_json}")
        sys.exit(1)

    try:
        caminho_saida = enriquecer_perfis(caminho_json)
    except RuntimeError as erro:
        print(f"Erro: {erro}")
        sys.exit(1)

    print(f"Perfis enriquecidos salvos em: {caminho_saida}")


if __name__ == "__main__":
    main()
