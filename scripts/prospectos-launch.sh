#!/usr/bin/env bash
# Abre o ProspectOS no Linux: sobe Docker Compose (se preciso) e abre o navegador.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
URL="${PROSPECTOS_URL:-http://127.0.0.1:5000}"
HEALTH="$URL/api/metricas"
COMPOSE=(docker compose -f "$ROOT/docker-compose.yml")

notify() {
  local titulo="$1" corpo="$2"
  if command -v notify-send >/dev/null 2>&1; then
    notify-send --app-name=ProspectOS -i prospectos "$titulo" "$corpo" || true
  fi
}

die() {
  notify "ProspectOS" "$1"
  # Zenity/kdialog se existirem; senão stderr
  if command -v zenity >/dev/null 2>&1; then
    zenity --error --title=ProspectOS --text="$1" 2>/dev/null || true
  elif command -v kdialog >/dev/null 2>&1; then
    kdialog --error "$1" 2>/dev/null || true
  fi
  echo "ProspectOS: $1" >&2
  exit 1
}

abrir_navegador() {
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  elif command -v sensible-browser >/dev/null 2>&1; then
    sensible-browser "$URL" >/dev/null 2>&1 || true
  else
    echo "Abra manualmente: $URL"
  fi
}

ja_no_ar() {
  curl -fsS --max-time 2 "$HEALTH" >/dev/null 2>&1
}

if ! command -v docker >/dev/null 2>&1; then
  die "Docker não encontrado. Instale o Docker Engine + Compose e tente de novo."
fi

if ! docker info >/dev/null 2>&1; then
  die "O Docker está instalado, mas o daemon não está rodando. Inicie o serviço do Docker e tente de novo."
fi

cd "$ROOT"

if [[ ! -f "$ROOT/.env" ]]; then
  if [[ -f "$ROOT/backend/.env.example" ]]; then
    cp "$ROOT/backend/.env.example" "$ROOT/.env"
    notify "ProspectOS" "Criei o arquivo .env — edite e coloque ao menos uma chave de IA (Gemini/Groq/NVIDIA)."
  else
    die "Arquivo .env ausente e não há backend/.env.example para copiar."
  fi
fi

if ja_no_ar; then
  abrir_navegador
  exit 0
fi

notify "ProspectOS" "Iniciando… isso pode levar um minuto na primeira vez."

# --build só quando a imagem ainda não existe (primeira execução / após pull)
if ! docker image inspect prospectos-app >/dev/null 2>&1; then
  "${COMPOSE[@]}" up -d --build || die "Falha ao construir/iniciar o ProspectOS. Veja o terminal ou: docker compose logs"
else
  "${COMPOSE[@]}" up -d || die "Falha ao iniciar o ProspectOS. Veja: docker compose -f \"$ROOT/docker-compose.yml\" logs"
fi

# Aguarda a API responder (até ~3 min)
for _ in $(seq 1 90); do
  if ja_no_ar; then
    notify "ProspectOS" "Pronto — abrindo no navegador."
    abrir_navegador
    exit 0
  fi
  sleep 2
done

die "O container subiu, mas a interface não respondeu a tempo. Confira: docker compose -f \"$ROOT/docker-compose.yml\" logs -f"
