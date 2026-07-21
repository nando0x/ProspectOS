"""Jobs de background (busca no Maps e análise de post do Instagram).

O estado "vivo" fica em dicts em memória (`estado_busca`/`estado_instagram`) -
é o que as rotas de status servem ao frontend a cada 2s. Cada execução também é
persistida na tabela `jobs`, então um restart do backend não apaga o histórico:
jobs que estavam rodando ficam marcados como 'interrompido' (base pra retomada
na fase 3).
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import db
import ia
import processar
from paths import DIR_DADOS, DIR_RECURSOS, caminho_recurso

logger = logging.getLogger(__name__)

# recursos read-only (código do instagram, scraper .exe) ficam junto do app;
# tudo que os jobs ESCREVEM (queries.txt, saidas/) vai pra área de dados
APP_DIR = DIR_RECURSOS
PASTA_INSTAGRAM = DIR_RECURSOS / "instagram"
sys.path.insert(0, str(PASTA_INSTAGRAM))

TIMEOUT_SCRAPER_SEGUNDOS = 900  # 15 minutos - nunca deve travar pra sempre

# guarda o estado da busca em andamento (pra não deixar disparar duas ao mesmo tempo
# e pra interface conseguir perguntar "já terminou?"). "etapa" e os contadores dão
# um progresso ao vivo em vez de só uma mensagem estática.
estado_busca = {
    "rodando": False,
    "mensagem": "",
    "etapa": "",  # "scraping" | "verificando_sites" | ""
    "empresas_encontradas": 0,
    "empresas_processadas": 0,
    # busca por mapa: qual área (pino) está sendo processada agora
    "area_atual": 0,
    "total_areas": 0,
}

# mesmo papel de estado_busca, mas para a análise de um post do Instagram
# (raspar comentários + enriquecer perfis dos autores únicos).
estado_instagram = {
    "rodando": False,
    "mensagem": "",
    "etapa": "",  # "raspando" | "enriquecendo" | ""
    "perfis_encontrados": 0,
    "perfis_processados": 0,
    "post_id": None,
}

# protegem o check-and-set da flag "rodando": sem eles, dois POSTs simultâneos
# passariam ambos pela checagem e disparariam dois jobs ao mesmo tempo
_lock_estado_busca = threading.Lock()
_lock_estado_instagram = threading.Lock()

# id (na tabela jobs) do job atualmente em execução de cada tipo - só existe um
# por vez de cada, garantido pelas flags "rodando"
_job_id_busca = None
_job_id_instagram = None


# ---------------------------------------------------------------------------
# Persistência na tabela jobs
# ---------------------------------------------------------------------------

def _agora():
    return datetime.now().isoformat(timespec="seconds")


def _registrar_inicio_job(tipo, referencia_id=None):
    conexao = db.conectar()
    try:
        cursor = conexao.execute(
            "INSERT INTO jobs (tipo, status, iniciado_em, atualizado_em, referencia_id) "
            "VALUES (?, 'rodando', ?, ?, ?)",
            (tipo, _agora(), _agora(), referencia_id),
        )
        conexao.commit()
        return cursor.lastrowid
    finally:
        conexao.close()


def _atualizar_job(job_id, etapa=None, mensagem=None, progresso_atual=None, progresso_total=None):
    if job_id is None:
        return
    atribuicoes = ["atualizado_em = ?"]
    parametros = [_agora()]
    for coluna, valor in (
        ("etapa", etapa),
        ("mensagem", mensagem),
        ("progresso_atual", progresso_atual),
        ("progresso_total", progresso_total),
    ):
        if valor is not None:
            atribuicoes.append(f"{coluna} = ?")
            parametros.append(valor)
    parametros.append(job_id)

    conexao = db.conectar()
    try:
        conexao.execute(f"UPDATE jobs SET {', '.join(atribuicoes)} WHERE id = ?", parametros)
        conexao.commit()
    except Exception:
        logger.exception("não foi possível atualizar o registro do job %s", job_id)
    finally:
        conexao.close()


def _finalizar_job(job_id, status, mensagem=None):
    if job_id is None:
        return
    conexao = db.conectar()
    try:
        conexao.execute(
            "UPDATE jobs SET status = ?, mensagem = COALESCE(?, mensagem), "
            "atualizado_em = ?, finalizado_em = ? WHERE id = ?",
            (status, mensagem, _agora(), _agora(), job_id),
        )
        conexao.commit()
    except Exception:
        logger.exception("não foi possível finalizar o registro do job %s", job_id)
    finally:
        conexao.close()


def marcar_jobs_interrompidos():
    """Chamado no startup: qualquer job que ficou como 'rodando' no banco morreu
    junto com o processo anterior (as threads não sobrevivem a um restart)."""
    conexao = db.conectar()
    try:
        cursor = conexao.execute(
            "UPDATE jobs SET status = 'interrompido', atualizado_em = ?, finalizado_em = ? "
            "WHERE status = 'rodando'",
            (_agora(), _agora()),
        )
        conexao.commit()
        if cursor.rowcount:
            logger.warning(
                "%s job(s) estavam rodando quando o backend foi encerrado - marcados como interrompidos",
                cursor.rowcount,
            )
    finally:
        conexao.close()


# ---------------------------------------------------------------------------
# Reserva/liberação das flags "rodando" (usadas pelas rotas de disparo)
# ---------------------------------------------------------------------------

def tentar_reservar_busca():
    with _lock_estado_busca:
        if estado_busca["rodando"]:
            return False
        estado_busca["rodando"] = True
        return True


def liberar_busca():
    estado_busca["rodando"] = False


def tentar_reservar_analise_instagram():
    with _lock_estado_instagram:
        if estado_instagram["rodando"]:
            return False
        estado_instagram["rodando"] = True
        return True


def liberar_analise_instagram():
    estado_instagram["rodando"] = False


def iniciar_thread_busca(areas=None):
    """`areas` (opcional) liga o modo mapa: lista de dicts {lat, lng, raio_m, rotulo} -
    o scraper roda uma vez por área, com as flags de geolocalização."""
    threading.Thread(target=_rodar_busca_em_background, args=(areas,), daemon=True).start()


def iniciar_thread_analise_instagram(post_id, post_url, nicho_alvo, arquivo_comentarios=None):
    threading.Thread(
        target=_rodar_analise_instagram_em_background,
        args=(post_id, post_url, nicho_alvo, arquivo_comentarios),
        daemon=True,
    ).start()


# ---------------------------------------------------------------------------
# Busca no Google Maps (scraper + processamento)
# ---------------------------------------------------------------------------

def traduzir_erro_scraper(stderr, returncode):
    """Converte a saída crua do scraper (ou timeout) numa mensagem que o usuário leigo entende."""
    texto = (stderr or "").lower()

    if "could not install driver" in texto or "playwright" in texto:
        return (
            "O scraper não conseguiu iniciar o navegador interno. Confira se o Node.js está "
            "instalado (veja o LEIA-ME.md) e tente novamente."
        )
    if "no such file" in texto or "not found" in texto:
        return f"O programa {nome_executavel_scraper()} não foi encontrado na pasta do projeto."
    if "deadline exceeded" in texto or "timeout" in texto:
        return "A busca no Google Maps demorou demais e foi interrompida. Tente de novo."

    return (
        f"A busca falhou (código {returncode}). Veja os detalhes completos em logs/prospeccao.log."
    )


def _ler_stderr_em_thread(pipe, buffer_lista):
    """Lê stderr continuamente numa thread separada, pra não bloquear o pipe
    (senão o processo trava se encher o buffer de stderr enquanto só lemos stdout)."""
    for linha in iter(pipe.readline, ""):
        buffer_lista.append(linha)
    pipe.close()


def rodar_scraper_com_progresso(comando, cwd, env, timeout_segundos, callback_linha=None):
    """Roda o scraper igual subprocess.run(), mas lê o stdout linha a linha em tempo
    real (em vez de esperar o processo inteiro terminar), chamando callback_linha
    a cada linha - é isso que alimenta o contador de progresso ao vivo."""
    processo = subprocess.Popen(
        comando,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    stderr_linhas = []
    thread_stderr = threading.Thread(
        target=_ler_stderr_em_thread, args=(processo.stderr, stderr_linhas), daemon=True
    )
    thread_stderr.start()

    inicio = time.monotonic()
    try:
        for linha in processo.stdout:
            if time.monotonic() - inicio > timeout_segundos:
                processo.kill()
                processo.wait(timeout=5)
                raise subprocess.TimeoutExpired(comando, timeout_segundos)

            if callback_linha:
                callback_linha(linha)

        tempo_restante = max(1, timeout_segundos - (time.monotonic() - inicio))
        returncode = processo.wait(timeout=tempo_restante)
    except subprocess.TimeoutExpired:
        processo.kill()
        processo.wait(timeout=5)
        raise
    finally:
        processo.stdout.close()
        thread_stderr.join(timeout=5)

    return returncode, "".join(stderr_linhas)


def _processar_linha_de_progresso_scraper(linha_texto):
    linha_texto = linha_texto.strip()
    if not linha_texto:
        return
    try:
        evento = json.loads(linha_texto)
    except json.JSONDecodeError:
        return  # linha não-JSON (algum log solto do binário) - ignora

    mensagem = evento.get("message", "")
    if mensagem == "job finished":
        estado_busca["empresas_processadas"] += 1
        estado_busca["mensagem"] = (
            f"Buscando no Google Maps... {estado_busca['empresas_processadas']} empresa(s) processada(s)"
        )
    elif mensagem.endswith("places found"):
        partes = mensagem.split(" ", 1)
        if partes[0].isdigit():
            estado_busca["empresas_encontradas"] += int(partes[0])


def _callback_progresso_verificacao(indice, total, nome_empresa):
    estado_busca["etapa"] = "verificando_sites"
    estado_busca["mensagem"] = f"Verificando site da empresa {indice} de {total}: {nome_empresa}"
    estado_busca["empresas_processadas"] = indice
    estado_busca["empresas_encontradas"] = total
    _atualizar_job(_job_id_busca, etapa="verificando_sites", progresso_atual=indice, progresso_total=total)


def zoom_para_raio(raio_m):
    """Nível de zoom do Google Maps compatível com o raio escolhido: raio maior
    exige zoom menor pra área caber na janela de busca. 1km→15, 5km→13, 50km→9."""
    import math
    return max(8, min(17, round(15 - math.log2(max(raio_m, 500) / 1000))))


def nome_executavel_scraper():
    """Nome do binário local do gosom/google-maps-scraper para a plataforma atual."""
    return "google-maps-scraper.exe" if sys.platform.startswith("win") else "google-maps-scraper"


def caminho_executavel_scraper():
    return caminho_recurso(nome_executavel_scraper())


def caminho_node_padrao(ambiente):
    """Resolve o Node usado pelo Playwright do scraper sem assumir Windows.

    Ordem: configuração salva → variável de ambiente → Node portátil empacotado
    → node do PATH → fallback clássico do Windows.
    """
    nome_node_embutido = "node.exe" if sys.platform.startswith("win") else "node"
    node_embutido = caminho_recurso("node", nome_node_embutido)
    node_no_path = shutil.which("node")
    return (
        db.obter_config("node_path")
        or ambiente.get("PLAYWRIGHT_NODEJS_PATH")
        or (str(node_embutido) if node_embutido.exists() else None)
        or node_no_path
        or (r"C:\Program Files\nodejs\node.exe" if sys.platform.startswith("win") else None)
    )


def _executar_scraper(arquivo_bruto, ambiente, flags_extras=()):
    """Roda o binário do scraper uma vez, com progresso ao vivo.
    Retorna None em sucesso, ou a mensagem de erro amigável em falha."""
    comando_scraper = [
        str(caminho_executavel_scraper()),
        "-input", str(DIR_DADOS / "queries.txt"),
        "-results", str(arquivo_bruto),
        "-lang", "pt",
        "-depth", "5",
        "-exit-on-inactivity", "3m",
        *flags_extras,
    ]
    proxies = db.obter_config("scraper_proxies")
    if proxies:
        comando_scraper += ["-proxies", proxies]

    try:
        # cwd precisa ser GRAVÁVEL: o scraper cria arquivos de trabalho (cache do
        # Playwright etc.) - empacotado, a pasta do app é read-only, então usamos
        # a área de dados
        returncode, stderr_completo = rodar_scraper_com_progresso(
            comando=comando_scraper,
            cwd=str(DIR_DADOS),
            env=ambiente,
            timeout_segundos=TIMEOUT_SCRAPER_SEGUNDOS,
            callback_linha=_processar_linha_de_progresso_scraper,
        )
    except subprocess.TimeoutExpired:
        logger.error("scraper excedeu o tempo limite de %ss", TIMEOUT_SCRAPER_SEGUNDOS)
        return (
            "A busca demorou demais e foi cancelada. Tente com menos nichos por vez, "
            "ou confira sua conexão com a internet."
        )
    except FileNotFoundError:
        logger.exception("%s não encontrado", nome_executavel_scraper())
        return f"O programa {nome_executavel_scraper()} não foi encontrado na pasta do projeto."

    if returncode != 0:
        logger.error("scraper falhou (código %s). stderr: %s", returncode, stderr_completo[-2000:])
        return traduzir_erro_scraper(stderr_completo, returncode)
    return None


CHAVES_CONTAGENS_SOMADAS = (
    "total_no_csv", "novos", "novos_sem_site", "novos_site_ruim",
    "descartados_por_site_ok", "descartados_nota_baixa",
    "descartados_sem_telefone", "erros_de_linha",
)

DICA_FONTE_PLACES = (
    " Dica: em Configurações → Fonte de dados você pode usar a Google Places API "
    "oficial, que é mais estável que o scraper."
)


def montar_mensagem_conclusao(contagens):
    """Mensagem final com o funil completo: quantas empresas foram capturadas,
    quantas viraram leads e POR QUE as demais ficaram de fora. Sem essa
    transparência o usuário compara com o que vê no Google ("lá tem 20, aqui
    puxou 2") e conclui que a busca está bugada."""
    total = contagens["total_no_csv"]
    novos = contagens["novos"]

    descartes = []
    if contagens.get("descartados_por_site_ok"):
        descartes.append(f"{contagens['descartados_por_site_ok']} já têm site bom (não precisam de você)")
    if contagens.get("descartados_nota_baixa"):
        descartes.append(f"{contagens['descartados_nota_baixa']} com nota baixa ou sem avaliações")
    if contagens.get("descartados_sem_telefone"):
        descartes.append(f"{contagens['descartados_sem_telefone']} sem telefone pra contato")

    ja_conhecidos = total - novos - sum((
        contagens.get("descartados_por_site_ok", 0),
        contagens.get("descartados_nota_baixa", 0),
        contagens.get("descartados_sem_telefone", 0),
        contagens.get("erros_de_linha", 0),
    ))
    if ja_conhecidos > 0:
        descartes.append(f"{ja_conhecidos} já estavam na sua base (dados atualizados)")

    detalhe_funil = f" Das {total} empresas capturadas: " + "; ".join(descartes) + "." if descartes else ""

    if novos == 0:
        return "Busca concluída: nenhum lead novo desta vez." + detalhe_funil
    return (
        f"Busca concluída: {novos} lead(s) novo(s) - "
        f"{contagens['novos_sem_site']} sem site e {contagens['novos_site_ruim']} com site ruim!"
        + detalhe_funil
    )


def _ler_queries_da_busca():
    """Lê as queries gravadas pela rota de disparo (uma por linha)."""
    try:
        texto = (DIR_DADOS / "queries.txt").read_text(encoding="utf-8")
    except OSError:
        return []
    return [linha.strip() for linha in texto.splitlines() if linha.strip()]


def _capturar_dados_brutos(arquivo_bruto, ambiente, area=None):
    """Gera o CSV bruto na fonte configurada: scraper local (padrão) ou Google
    Places API. As duas escrevem o MESMO formato de CSV, então o resto do
    pipeline não muda. Retorna None em sucesso ou a mensagem de erro amigável."""
    fonte = db.obter_config("fonte_maps") or "scraper"

    if fonte == "places":
        import fontes_maps

        chave = db.obter_config("places")
        if not chave:
            return (
                "A fonte Google Places API está selecionada, mas nenhuma chave foi "
                "configurada. Salve a chave em Configurações → Fonte de dados."
            )
        queries = _ler_queries_da_busca()
        if not queries:
            return "Nenhuma busca encontrada. Dispare a busca novamente."

        def progresso(indice, total, texto):
            estado_busca["mensagem"] = f"Consultando o Google Places... busca {indice} de {total}: {texto}"

        try:
            encontrados = fontes_maps.buscar_com_places_api(
                queries, arquivo_bruto, chave, area=area, callback_query=progresso
            )
        except fontes_maps.ErroPlacesApi as erro:
            return str(erro)
        estado_busca["empresas_encontradas"] += encontrados
        return None

    flags_geo = ()
    if area:
        flags_geo = (
            "-geo", f"{area['lat']},{area['lng']}",
            "-radius", str(area["raio_m"]),
            "-zoom", str(zoom_para_raio(area["raio_m"])),
        )
    return _executar_scraper(arquivo_bruto, ambiente, flags_geo)


def _buscar_por_areas(areas, ambiente, data):
    """Modo mapa: roda a fonte uma vez por área (pino + raio), processando cada
    resultado com a cidade/rótulo do pino. Uma área que falha não derruba as
    outras - vira um aviso no resultado final. Retorna as contagens somadas, ou
    None se TODAS as áreas falharem (mensagem de erro já definida no estado)."""
    total = {chave: 0 for chave in CHAVES_CONTAGENS_SOMADAS}
    avisos = []
    alguma_area_ok = False

    for i, area in enumerate(areas, start=1):
        rotulo = area["rotulo"]
        estado_busca["area_atual"] = i
        estado_busca["etapa"] = "scraping"
        estado_busca["mensagem"] = f"Área {i} de {len(areas)} ({rotulo}): buscando no Google Maps..."
        _atualizar_job(
            _job_id_busca, etapa="scraping", mensagem=estado_busca["mensagem"],
            progresso_atual=i, progresso_total=len(areas),
        )

        arquivo_bruto = DIR_DADOS / "saidas" / f"bruto_{data}_area{i}.csv"
        erro = _capturar_dados_brutos(arquivo_bruto, ambiente, area=area)
        if erro:
            avisos.append(f'área "{rotulo}": {erro}')
            continue

        estado_busca["etapa"] = "verificando_sites"
        estado_busca["mensagem"] = f"Área {i} de {len(areas)} ({rotulo}): filtrando leads e gerando WhatsApp..."
        estado_busca["empresas_processadas"] = 0
        contagens = processar.processar(
            arquivo_bruto,
            callback_progresso=_callback_progresso_verificacao,
            cidade_padrao=rotulo,
            sufixo_saida=f"_{data}_area{i}",
        )
        for chave in CHAVES_CONTAGENS_SOMADAS:
            total[chave] += contagens.get(chave, 0)
        alguma_area_ok = True

    if not alguma_area_ok:
        estado_busca["mensagem"] = "A busca falhou em todas as áreas. " + " | ".join(avisos)
        if (db.obter_config("fonte_maps") or "scraper") == "scraper":
            estado_busca["mensagem"] += DICA_FONTE_PLACES
        return None

    total["avisos_areas"] = avisos
    return total


def _rodar_busca_em_background(areas=None):
    global _job_id_busca
    estado_busca["rodando"] = True
    estado_busca["mensagem"] = "Buscando no Google Maps..."
    estado_busca["etapa"] = "scraping"
    estado_busca["empresas_encontradas"] = 0
    estado_busca["empresas_processadas"] = 0
    estado_busca["area_atual"] = 0
    estado_busca["total_areas"] = len(areas) if areas else 0
    logger.info("busca iniciada (modo %s)", "mapa" if areas else "texto")
    _job_id_busca = _registrar_inicio_job("busca_maps")
    _atualizar_job(_job_id_busca, etapa="scraping", mensagem="Buscando no Google Maps...")
    status_final = "erro"

    try:
        db.fazer_backup_banco()

        data = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        pasta_saidas = DIR_DADOS / "saidas"
        pasta_saidas.mkdir(parents=True, exist_ok=True)

        # caminho do Node usado pelo Playwright embutido no scraper: pode vir da
        # tabela configuracoes (chave "node_path"), da variável de ambiente, do
        # Node portátil distribuído junto com o app empacotado, do PATH ou do local
        # padrão de instalação do Windows.
        ambiente = os.environ.copy()
        node_padrao = caminho_node_padrao(ambiente)
        if node_padrao:
            ambiente["PLAYWRIGHT_NODEJS_PATH"] = node_padrao

        if areas:
            contagens = _buscar_por_areas(areas, ambiente, data)
            if contagens is None:
                return  # todas as áreas falharam - mensagem já definida
        else:
            arquivo_bruto = pasta_saidas / f"bruto_{data}.csv"
            erro = _capturar_dados_brutos(arquivo_bruto, ambiente)
            if erro:
                if (db.obter_config("fonte_maps") or "scraper") == "scraper":
                    erro += DICA_FONTE_PLACES
                estado_busca["mensagem"] = erro
                return

            estado_busca["mensagem"] = "Filtrando leads e gerando WhatsApp..."
            estado_busca["etapa"] = "verificando_sites"
            estado_busca["empresas_processadas"] = 0
            contagens = processar.processar(arquivo_bruto, callback_progresso=_callback_progresso_verificacao)

        fonte = db.obter_config("fonte_maps") or "scraper"
        if contagens["total_no_csv"] == 0:
            if estado_busca["empresas_encontradas"] == 0:
                estado_busca["mensagem"] = (
                    "Busca concluída, mas o Google Maps não retornou nenhum resultado - o scraper "
                    "rodou sem erro, só não conseguiu capturar nada. Isso geralmente é bloqueio "
                    "temporário do Google para o seu IP/rede (comum em VPN, rede corporativa ou "
                    "após várias buscas seguidas), não um erro de digitação. Tente novamente mais "
                    "tarde ou numa rede diferente."
                    + (DICA_FONTE_PLACES if fonte == "scraper" else "")
                )
            else:
                estado_busca["mensagem"] = (
                    "Busca concluída, mas nenhuma empresa foi encontrada. Confira se o nicho/cidade "
                    "estão escritos corretamente."
                )
        else:
            estado_busca["mensagem"] = montar_mensagem_conclusao(contagens)

        avisos_areas = contagens.get("avisos_areas") or []
        if avisos_areas:
            estado_busca["mensagem"] += " Atenção: " + " | ".join(avisos_areas)

        status_final = "concluido"
        logger.info("busca concluída: %s", contagens)

    except Exception:
        logger.exception("erro inesperado durante a busca")
        estado_busca["mensagem"] = "Ocorreu um erro inesperado. Veja detalhes em logs/prospeccao.log."
    finally:
        estado_busca["rodando"] = False
        estado_busca["etapa"] = ""
        estado_busca["area_atual"] = 0
        _finalizar_job(_job_id_busca, status_final, estado_busca["mensagem"])
        _job_id_busca = None


# ---------------------------------------------------------------------------
# Análise de post do Instagram (raspar comentários + enriquecer + classificar)
# ---------------------------------------------------------------------------

def _callback_progresso_enriquecimento_instagram(indice, total, username):
    estado_instagram["etapa"] = "enriquecendo"
    estado_instagram["mensagem"] = f"Consultando perfil {indice} de {total}: @{username}"
    estado_instagram["perfis_processados"] = indice
    estado_instagram["perfis_encontrados"] = total
    _atualizar_job(_job_id_instagram, etapa="enriquecendo", progresso_atual=indice, progresso_total=total)


def _rodar_analise_instagram_em_background(post_id, post_url, nicho_alvo=None, arquivo_comentarios=None):
    """Pipeline completo da análise. Se `arquivo_comentarios` vier preenchido
    (retomada de uma análise interrompida), pula a raspagem e reaproveita o JSON
    já salvo - o enriquecimento, por sua vez, retoma do parcial salvo em disco."""
    global _job_id_instagram
    retomada = bool(arquivo_comentarios)
    estado_instagram["rodando"] = True
    estado_instagram["mensagem"] = (
        "Retomando análise de onde parou..." if retomada else "Extraindo comentários do post..."
    )
    estado_instagram["etapa"] = "raspando"
    estado_instagram["perfis_encontrados"] = 0
    estado_instagram["perfis_processados"] = 0
    estado_instagram["post_id"] = post_id
    logger.info("análise do Instagram iniciada para post_id=%s (retomada=%s)", post_id, retomada)
    _job_id_instagram = _registrar_inicio_job("analise_instagram", referencia_id=post_id)
    _atualizar_job(_job_id_instagram, etapa="raspando", mensagem=estado_instagram["mensagem"])
    status_final = "erro"

    def marcar_erro(mensagem):
        estado_instagram["mensagem"] = mensagem
        conexao = db.conectar()
        try:
            conexao.execute(
                "UPDATE instagram_posts SET etapa = 'erro', erro_mensagem = ? WHERE id = ?",
                (mensagem, post_id),
            )
            conexao.commit()
        finally:
            conexao.close()

    try:
        import raspar_comentarios
        import enriquecer_perfis

        conexao = db.conectar()
        try:
            conexao.execute("UPDATE instagram_posts SET etapa = 'raspando' WHERE id = ?", (post_id,))
            conexao.commit()
        finally:
            conexao.close()

        if retomada:
            caminho_comentarios = Path(arquivo_comentarios)
        else:
            try:
                caminho_comentarios = raspar_comentarios.raspar_comentarios(post_url)
            except RuntimeError as erro:
                marcar_erro(str(erro))
                return
            except Exception as erro:
                marcar_erro(f"Erro ao acessar o post (pode ser privado, removido, ou rate limit): {erro}")
                return

            # guarda o caminho do JSON raspado: é o que permite retomar esta
            # análise depois sem raspar o post de novo
            conexao = db.conectar()
            try:
                conexao.execute(
                    "UPDATE instagram_posts SET arquivo_comentarios = ? WHERE id = ?",
                    (str(caminho_comentarios), post_id),
                )
                conexao.commit()
            finally:
                conexao.close()

        dados_comentarios = json.loads(Path(caminho_comentarios).read_text(encoding="utf-8"))

        estado_instagram["mensagem"] = "Enriquecendo perfis dos autores dos comentários..."
        estado_instagram["etapa"] = "enriquecendo"
        _atualizar_job(_job_id_instagram, etapa="enriquecendo")

        conexao = db.conectar()
        try:
            conexao.execute(
                "UPDATE instagram_posts SET etapa = 'enriquecendo', total_comentarios = ? WHERE id = ?",
                (dados_comentarios["total_comentarios"], post_id),
            )
            conexao.commit()
        finally:
            conexao.close()

        try:
            caminho_enriquecido = enriquecer_perfis.enriquecer_perfis(
                Path(caminho_comentarios), callback_progresso=_callback_progresso_enriquecimento_instagram
            )
        except RuntimeError as erro:
            marcar_erro(str(erro))
            return

        dados_enriquecidos = json.loads(Path(caminho_enriquecido).read_text(encoding="utf-8"))

        estado_instagram["mensagem"] = "Classificando perfis com IA..."
        estado_instagram["etapa"] = "classificando"
        _atualizar_job(_job_id_instagram, etapa="classificando")
        total_perfis = len(dados_enriquecidos["perfis"])
        classificacoes = {}
        for indice, perfil in enumerate(dados_enriquecidos["perfis"], start=1):
            estado_instagram["mensagem"] = f"Classificando perfil {indice} de {total_perfis}: @{perfil.get('username')}"
            if perfil.get("is_private"):
                continue  # mesma regra do prompt manual: descarta privados sem gastar chamada de IA
            if perfil.get("erro"):
                continue  # coleta do perfil falhou (rate limit, sessão expirada etc.) - não há dado real pra classificar
            if ia.perfil_tem_site_proprio(perfil):
                continue  # já tem site próprio na bio - não é o perfil de lead que buscamos
            try:
                classificacoes[perfil["username"]] = ia.classificar_lead_instagram_com_fallback(perfil, nicho_alvo)
            except Exception as erro:
                logger.warning("classificação por IA falhou para @%s, seguindo sem prioridade: %s", perfil.get("username"), erro)

        conexao = db.conectar()
        try:
            for perfil in dados_enriquecidos["perfis"]:
                classificacao = classificacoes.get(perfil["username"], {})
                tem_site_proprio = ia.perfil_tem_site_proprio(perfil)
                observacoes = (
                    f"Perfil não avaliado - falha na coleta: {perfil['erro']}"
                    if perfil.get("erro")
                    else "Perfil ignorado automaticamente - já tem site próprio na bio."
                    if tem_site_proprio
                    else None
                )
                status_inicial = (
                    "ignorado"
                    if perfil.get("is_private") or tem_site_proprio
                    else "novo"
                )
                agora = datetime.now().isoformat(timespec="seconds")

                # A mesma pessoa pode comentar em posts diferentes: cada username
                # existe uma única vez no banco. Se o lead já existe, mescla os
                # comentários novos e atualiza os dados "vivos" do perfil, mas
                # nunca mexe no que é do usuário (status, tags, observações,
                # follow-up) - mesma filosofia do upsert dos leads do Maps.
                existente = conexao.execute(
                    "SELECT comentarios FROM instagram_leads WHERE username = ?",
                    (perfil["username"],),
                ).fetchone()

                comentarios_novos = perfil.get("comentarios", [])
                if existente:
                    try:
                        comentarios_antigos = json.loads(existente["comentarios"] or "[]")
                    except (TypeError, json.JSONDecodeError):
                        comentarios_antigos = []
                    comentarios_mesclados = comentarios_antigos + [
                        c for c in comentarios_novos if c not in comentarios_antigos
                    ]

                    if perfil.get("erro"):
                        # a coleta falhou nesta rodada: não sobrescreve com None
                        # os dados bons já salvos, só junta os comentários novos
                        conexao.execute(
                            "UPDATE instagram_leads SET post_id = ?, comentarios = ?, atualizado_em = ? "
                            "WHERE username = ?",
                            (
                                post_id,
                                json.dumps(comentarios_mesclados, ensure_ascii=False),
                                agora,
                                perfil["username"],
                            ),
                        )
                    else:
                        conexao.execute(
                            """
                            UPDATE instagram_leads SET
                                post_id = ?, full_name = ?, is_private = ?, biography = ?,
                                seguidores = ?, is_business_account = ?, comentarios = ?,
                                prioridade = COALESCE(?, prioridade),
                                nicho = COALESCE(?, nicho),
                                justificativa = COALESCE(?, justificativa),
                                sugestao_dm = COALESCE(?, sugestao_dm),
                                atualizado_em = ?
                            WHERE username = ?
                            """,
                            (
                                post_id,
                                perfil.get("full_name"),
                                int(bool(perfil.get("is_private"))) if "is_private" in perfil else None,
                                perfil.get("biography"),
                                perfil.get("seguidores"),
                                int(bool(perfil.get("is_business_account"))) if "is_business_account" in perfil else None,
                                json.dumps(comentarios_mesclados, ensure_ascii=False),
                                classificacao.get("prioridade"),
                                classificacao.get("nicho"),
                                classificacao.get("justificativa"),
                                classificacao.get("sugestao_dm"),
                                agora,
                                perfil["username"],
                            ),
                        )
                else:
                    conexao.execute(
                        """
                        INSERT INTO instagram_leads
                            (post_id, username, full_name, is_private, biography, seguidores, is_business_account, comentarios,
                             prioridade, nicho, justificativa, sugestao_dm, observacoes, status, atualizado_em)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            post_id,
                            perfil["username"],
                            perfil.get("full_name"),
                            int(bool(perfil.get("is_private"))) if "is_private" in perfil else None,
                            perfil.get("biography"),
                            perfil.get("seguidores"),
                            int(bool(perfil.get("is_business_account"))) if "is_business_account" in perfil else None,
                            json.dumps(comentarios_novos, ensure_ascii=False),
                            classificacao.get("prioridade"),
                            classificacao.get("nicho"),
                            classificacao.get("justificativa"),
                            classificacao.get("sugestao_dm"),
                            observacoes,
                            status_inicial,
                            agora,
                        ),
                    )
            conexao.execute(
                "UPDATE instagram_posts SET etapa = 'concluido', total_perfis = ? WHERE id = ?",
                (len(dados_enriquecidos["perfis"]), post_id),
            )
            conexao.commit()
        finally:
            conexao.close()

        estado_instagram["mensagem"] = f"Análise concluída: {len(dados_enriquecidos['perfis'])} perfil(is) encontrado(s)."
        status_final = "concluido"
        logger.info("análise do Instagram concluída para post_id=%s", post_id)

    except Exception:
        logger.exception("erro inesperado na análise do Instagram")
        marcar_erro("Ocorreu um erro inesperado. Veja detalhes em logs/prospeccao.log.")
    finally:
        estado_instagram["rodando"] = False
        estado_instagram["etapa"] = ""
        _finalizar_job(_job_id_instagram, status_final, estado_instagram["mensagem"])
        _job_id_instagram = None
