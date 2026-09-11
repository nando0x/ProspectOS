#!/usr/bin/env bash
# Sobe backend (:5000) + frontend dev (:5173) e abre o navegador — espelho do iniciar.bat
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASTA_BACKEND="$ROOT/backend"
PASTA_FRONTEND="$ROOT/frontend"
PASTA_LOGS="$ROOT/logs"

mkdir -p "$PASTA_LOGS"

backend_rodando() {
  curl -fsS --max-time 1 "http://127.0.0.1:5000/api/metricas" >/dev/null 2>&1
}

frontend_rodando() {
  curl -fsS --max-time 1 "http://127.0.0.1:5173" >/dev/null 2>&1
}

echo "Verificando se o backend já está rodando..."
if backend_rodando; then
  echo "Backend já estava rodando."
else
  echo "Iniciando o backend..."
  (cd "$PASTA_BACKEND" && python3 app.py >>"$PASTA_LOGS/backend-saida.log" 2>>"$PASTA_LOGS/backend-erro.log") &
fi

echo "Verificando se a interface já está rodando..."
if frontend_rodando; then
  echo "Interface já estava rodando."
else
  echo "Iniciando a interface..."
  (cd "$PASTA_FRONTEND" && npm run dev >>"$PASTA_LOGS/frontend-saida.log" 2>>"$PASTA_LOGS/frontend-erro.log") &
  sleep 4
fi

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:5173" >/dev/null 2>&1 || true
elif command -v sensible-browser >/dev/null 2>&1; then
  sensible-browser "http://localhost:5173" >/dev/null 2>&1 || true
else
  echo "Abra http://localhost:5173 no navegador."
fi
