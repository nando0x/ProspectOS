#!/usr/bin/env bash
# Prepara o driver do Playwright usado pelo google-maps-scraper (Linux/macOS).
#
# Por que isso existe: o binário do scraper embute uma versão do playwright-go que
# baixa o driver do CDN antigo (playwright.azureedge.net), que foi desativado e
# hoje responde 404 - a busca falha com "não conseguiu iniciar o navegador interno".
# O playwright-go moderno monta o driver a partir do pacote npm playwright-core;
# este script faz exatamente isso, à mão, no diretório que o binário já procura.
#
# Idempotente: se o driver já estiver no lugar, não faz nada.
# Uso: ./preparar_driver_playwright.sh
set -euo pipefail

VERSAO_DRIVER="${PLAYWRIGHT_GO_DRIVER_VERSION:-1.60.0}"
DIR_DRIVER="${HOME}/.cache/ms-playwright-go/${VERSAO_DRIVER}"
CLI_JS="${DIR_DRIVER}/package/cli.js"

if ! command -v node >/dev/null 2>&1; then
    echo "ERRO: Node.js não encontrado no PATH. Instale o Node e rode de novo." >&2
    exit 1
fi

if [ -f "$CLI_JS" ]; then
    echo "Driver do Playwright já preparado em $DIR_DRIVER"
else
    echo "Baixando playwright-core ${VERSAO_DRIVER} do npm..."
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    curl -fsSL --max-time 300 \
        -o "$TMP/core.tgz" \
        "https://registry.npmjs.org/playwright-core/-/playwright-core-${VERSAO_DRIVER}.tgz"

    mkdir -p "$DIR_DRIVER"
    # o tarball do npm aninha tudo sob "package/", que é o layout que o
    # playwright-go espera (<driver>/package/cli.js)
    tar -xzf "$TMP/core.tgz" -C "$DIR_DRIVER"

    if [ ! -f "$CLI_JS" ]; then
        echo "ERRO: extração falhou - $CLI_JS não existe." >&2
        exit 1
    fi
    echo "Driver instalado em $DIR_DRIVER"
fi

# o binário procura um node dentro do diretório do driver quando
# PLAYWRIGHT_NODEJS_PATH não está definido
ln -sf "$(command -v node)" "${DIR_DRIVER}/node"

echo "Baixando navegadores (pulado se já existirem)..."
node "$CLI_JS" install chromium

echo "Pronto. O scraper do Google Maps já consegue subir o navegador."
