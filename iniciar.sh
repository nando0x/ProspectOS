#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PASTA_BACKEND="$PWD/backend"
PASTA_FRONTEND="$PWD/frontend"
PASTA_LOGS="$PWD/logs"
PYTHON_BIN="${PYTHON_BIN:-}"

mkdir -p "$PASTA_LOGS"

if [ -z "$PYTHON_BIN" ]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="python3.11"
  else
    PYTHON_BIN="python3"
  fi
fi

echo "Verificando se o backend ja esta rodando..."
if curl -fsS --max-time 1 http://127.0.0.1:5000/api/metricas >/dev/null 2>&1; then
  echo "Backend ja estava rodando."
else
  echo "Iniciando o backend..."
  (
    cd "$PASTA_BACKEND"
    nohup "$PYTHON_BIN" app.py > "$PASTA_LOGS/backend-saida.log" 2> "$PASTA_LOGS/backend-erro.log" < /dev/null &
  )
fi

echo "Verificando se a interface ja esta rodando..."
if curl -fsS --max-time 1 http://localhost:5173 >/dev/null 2>&1; then
  echo "Interface ja estava rodando."
else
  echo "Iniciando a interface..."
  (
    cd "$PASTA_FRONTEND"
    nohup npm run dev > "$PASTA_LOGS/frontend-saida.log" 2> "$PASTA_LOGS/frontend-erro.log" < /dev/null &
  )
  sleep 4
fi

URL="http://localhost:5173"
if command -v open >/dev/null 2>&1; then
  open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 || true
else
  echo "Abra $URL no navegador."
fi
