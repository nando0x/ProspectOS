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

Comportamento defensivo:
- o resultado parcial é salvo em disco a cada perfil consultado, então uma
  interrupção (checkpoint, rate limit, queda de luz) nunca perde progresso;
- rodar de novo com o mesmo JSON de comentários retoma de onde parou,
  pulando os perfis já consultados com sucesso;
- o intervalo entre consultas tem jitter (variação aleatória) e cresce
  exponencialmente quando o Instagram começa a reclamar, voltando ao normal
  quando as consultas voltam a funcionar;
- checkpoint/sessão expirada param a execução na hora (com o parcial salvo),
  em vez de queimar o resto da fila com erros e mais risco pra conta.
"""

import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    ClientError,
    LoginRequired,
    PleaseWaitFewMinutes,
    UserNotFound,
)

# permite achar o paths.py do backend também quando rodado standalone
sys.path.insert(0, str(Path(__file__).parent.parent))
from paths import DIR_DADOS  # noqa: E402

PASTA_SESSAO = DIR_DADOS / "instagram" / "sessao"
DELAY_BASE_SEGUNDOS = 8  # intervalo base entre consultas de perfil
DELAY_MAXIMO_SEGUNDOS = 90  # teto do backoff exponencial
FALHAS_DE_LIMITE_SEGUIDAS_PARA_PARAR = 3  # rate limits consecutivos antes de desistir


class AnaliseInterrompida(RuntimeError):
    """Interrupção controlada (checkpoint, sessão expirada ou rate limit
    persistente). O resultado parcial já está salvo em disco; rodar de novo
    retoma de onde parou."""


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


def agrupar_comentarios_por_usuario(comentarios: list[dict]) -> dict:
    agrupado = {}
    for comentario in comentarios:
        username = comentario["username"]
        agrupado.setdefault(username, []).append(comentario["texto"])
    return agrupado


def _carregar_parcial(caminho_saida: Path) -> list[dict]:
    """Perfis já consultados com sucesso numa rodada anterior (retomada).
    Entradas que deram erro na rodada anterior são descartadas - vale a pena
    tentar de novo, o erro pode ter sido só o rate limit da hora."""
    if not caminho_saida.exists():
        return []
    try:
        dados = json.loads(caminho_saida.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [p for p in dados.get("perfis", []) if not p.get("erro")]


def _salvar(caminho_saida: Path, post_url, perfis: list[dict]) -> None:
    resultado = {
        "post_url": post_url,
        "enriquecido_em": datetime.now().isoformat(timespec="seconds"),
        "perfis": perfis,
    }
    caminho_saida.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _dormir_com_jitter(delay_segundos: float) -> None:
    time.sleep(delay_segundos * random.uniform(0.7, 1.3))


def enriquecer_perfis(caminho_json: Path, callback_progresso=None) -> Path:
    dados = json.loads(caminho_json.read_text(encoding="utf-8"))
    comentarios_por_usuario = agrupar_comentarios_por_usuario(dados["comentarios"])

    caminho_saida = caminho_json.with_name(caminho_json.stem + "_enriquecido.json")
    perfis = _carregar_parcial(caminho_saida)
    usernames_prontos = {p["username"] for p in perfis}
    if usernames_prontos:
        print(f"Retomando: {len(usernames_prontos)} perfil(is) já consultado(s) em rodada anterior.")

    cliente = carregar_sessao()

    total = len(comentarios_por_usuario)
    delay_atual = DELAY_BASE_SEGUNDOS
    falhas_de_limite_seguidas = 0
    pendentes = [
        (username, textos)
        for username, textos in comentarios_por_usuario.items()
        if username not in usernames_prontos
    ]

    for i, (username, textos) in enumerate(pendentes, start=len(usernames_prontos) + 1):
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
            delay_atual = DELAY_BASE_SEGUNDOS  # voltou a funcionar: backoff zera
            falhas_de_limite_seguidas = 0
        except UserNotFound:
            item["erro"] = "perfil não encontrado (pode ter sido removido ou renomeado)"
        except (ChallengeRequired, LoginRequired) as erro:
            # parada imediata: insistir com sessão inválida/checkpoint só piora
            # a situação da conta. O parcial já salvo permite retomar depois.
            _salvar(caminho_saida, dados.get("post_url"), perfis)
            feitos = len(perfis)
            if isinstance(erro, ChallengeRequired):
                raise AnaliseInterrompida(
                    f"O Instagram pediu uma verificação de segurança (checkpoint) na sua conta. "
                    f"Análise pausada com {feitos} de {total} perfil(is) consultado(s). "
                    "Abra o Instagram no celular, resolva a verificação, rode py instagram\\login.py "
                    "de novo e use 'Retomar análise' - ela continua de onde parou."
                )
            raise AnaliseInterrompida(
                f"A sessão do Instagram expirou. Análise pausada com {feitos} de {total} "
                "perfil(is) consultado(s). Rode py instagram\\login.py <seu_usuario> e use "
                "'Retomar análise' - ela continua de onde parou."
            )
        except (PleaseWaitFewMinutes, ClientError) as erro:
            eh_limite = isinstance(erro, PleaseWaitFewMinutes) or "wait" in str(erro).lower() or "429" in str(erro)
            if eh_limite:
                falhas_de_limite_seguidas += 1
                delay_atual = min(delay_atual * 2, DELAY_MAXIMO_SEGUNDOS)
                if falhas_de_limite_seguidas >= FALHAS_DE_LIMITE_SEGUIDAS_PARA_PARAR:
                    _salvar(caminho_saida, dados.get("post_url"), perfis)
                    raise AnaliseInterrompida(
                        f"O Instagram está limitando as consultas (rate limit) mesmo com o ritmo "
                        f"reduzido. Análise pausada com {len(perfis)} de {total} perfil(is) "
                        "consultado(s) - espere ao menos 1 hora e use 'Retomar análise', ela "
                        "continua de onde parou."
                    )
                item["erro"] = f"perfil inacessível (rate limit): {erro}"
            else:
                item["erro"] = f"perfil inacessível (rate limit ou outro erro): {erro}"

        perfis.append(item)
        _salvar(caminho_saida, dados.get("post_url"), perfis)  # parcial a cada perfil

        if i < total:
            _dormir_com_jitter(delay_atual)

    _salvar(caminho_saida, dados.get("post_url"), perfis)
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
