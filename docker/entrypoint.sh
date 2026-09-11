#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="/app/backend"
SCRAPER="$BACKEND_DIR/google-maps-scraper"
BAIXAR="/app/scripts/baixar-scraper.sh"

mkdir -p "$PROSPECTOS_DATA_DIR"

if [[ ! -x "$SCRAPER" ]]; then
  echo "Scraper não encontrado — baixando binário Linux..."
  if [[ -x "$BAIXAR" ]]; then
    "$BAIXAR"
  else
    API_URL="https://api.github.com/repos/gosom/google-maps-scraper/releases/latest"
    JSON="$(curl -fsSL "$API_URL")"
    ASSET_URL="$(echo "$JSON" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for asset in data.get('assets', []):
    if 'linux-amd64' in asset.get('name', ''):
        print(asset['browser_download_url'])
        break
")"
    if [[ -z "$ASSET_URL" ]]; then
      echo "Falha ao localizar asset linux-amd64 do scraper." >&2
      exit 1
    fi
    curl -fsSL -o "$SCRAPER" "$ASSET_URL"
    chmod +x "$SCRAPER"
  fi
fi

cd "$BACKEND_DIR"
exec python3 app.py
