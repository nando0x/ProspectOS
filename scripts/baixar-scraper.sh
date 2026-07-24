#!/usr/bin/env bash
# Baixa o binário linux-amd64 do gosom/google-maps-scraper e instala em backend/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../backend" && pwd)"
DEST="$BACKEND_DIR/google-maps-scraper"
API_URL="https://api.github.com/repos/gosom/google-maps-scraper/releases/latest"

if [[ -x "$DEST" ]]; then
  echo "Scraper já existe em $DEST"
  exit 0
fi

echo "Buscando release mais recente..."
JSON="$(curl -fsSL "$API_URL")"

ASSET_URL="$(echo "$JSON" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for asset in data.get('assets', []):
    name = asset.get('name', '')
    if 'linux-amd64' in name and not name.endswith(('.tar.gz', '.zip')):
        print(asset['browser_download_url'])
        break
")"

if [[ -z "$ASSET_URL" ]]; then
  echo "Não encontrei asset linux-amd64 na release latest." >&2
  exit 1
fi

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

echo "Baixando $ASSET_URL ..."
curl -fsSL -o "$TMP" "$ASSET_URL"
chmod +x "$TMP"
mv "$TMP" "$DEST"
trap - EXIT

echo "Instalado em $DEST"
