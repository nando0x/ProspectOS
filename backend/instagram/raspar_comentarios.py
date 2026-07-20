"""
Extrai os comentários de um post do Instagram e salva em JSON.

Uso:
    py raspar_comentarios.py <url_do_post>

Requer sessão salva previamente com:
    py login.py <seu_usuario>
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    ClientError,
    LoginRequired,
    PleaseWaitFewMinutes,
)

# permite achar o paths.py do backend também quando rodado standalone
# (py raspar_comentarios.py) - importado pelo jobs.py, o backend já está no path
sys.path.insert(0, str(Path(__file__).parent.parent))
from paths import DIR_DADOS  # noqa: E402

# sessão e comentários são ESCRITOS pelo app - ficam na área de dados
PASTA_SESSAO = DIR_DADOS / "instagram" / "sessao"
PASTA_COMENTARIOS = DIR_DADOS / "instagram" / "comentarios"


def carregar_sessao() -> Client:
    arquivos_sessao = list(PASTA_SESSAO.glob("session-*.json"))
    if not arquivos_sessao:
        raise RuntimeError(
            "Nenhuma sessão do Instagram encontrada. "
            "Faça login em Configurações → Conta do Instagram."
        )
    cliente = Client()
    cliente.load_settings(arquivos_sessao[0])
    return cliente


def raspar_comentarios(url: str) -> Path:
    cliente = carregar_sessao()

    # traduz os erros de conta/sessão do instagrapi em mensagens claras ANTES
    # de qualquer retry - insistir com checkpoint/sessão inválida só aumenta o
    # risco de bloqueio da conta.
    try:
        media_pk = cliente.media_pk_from_url(url)
        comentarios_brutos = cliente.media_comments(media_pk, amount=0)
    except ChallengeRequired:
        raise RuntimeError(
            "O Instagram pediu uma verificação de segurança (checkpoint) na sua conta. "
            "Abra o Instagram no celular, resolva a verificação e rode py instagram\\login.py de novo."
        )
    except LoginRequired:
        raise RuntimeError(
            "A sessão do Instagram expirou ou foi invalidada. "
            "Rode de novo: py instagram\\login.py <seu_usuario>"
        )
    except PleaseWaitFewMinutes:
        raise RuntimeError(
            "O Instagram está limitando as requisições da sua conta agora (rate limit). "
            "Espere alguns minutos (de preferência 1 hora) e tente de novo."
        )

    comentarios = [
        {"username": c.user.username, "texto": c.text}
        for c in comentarios_brutos
    ]

    resultado = {
        "post_url": url,
        "capturado_em": datetime.now().isoformat(timespec="seconds"),
        "total_comentarios": len(comentarios),
        "comentarios": comentarios,
    }

    PASTA_COMENTARIOS.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"post_{media_pk}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    caminho_saida = PASTA_COMENTARIOS / nome_arquivo
    caminho_saida.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return caminho_saida


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: py raspar_comentarios.py <url_do_post>")
        sys.exit(1)

    url = sys.argv[1]

    try:
        caminho_saida = raspar_comentarios(url)
    except RuntimeError as erro:
        print(f"Erro: {erro}")
        sys.exit(1)
    except LoginRequired:
        print(
            "Erro: a sessão expirou ou foi invalidada. Rode de novo: "
            "py login.py <seu_usuario>"
        )
        sys.exit(1)
    except ClientError as erro:
        print(
            f"Erro ao acessar o post (pode ser privado, ter sido removido, "
            f"ou rate limit do Instagram): {erro}"
        )
        sys.exit(1)

    print(f"Comentários salvos em: {caminho_saida}")


if __name__ == "__main__":
    main()
