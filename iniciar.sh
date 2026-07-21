#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PASTA_BACKEND="$PWD/backend"
PASTA_FRONTEND="$PWD/frontend"
PASTA_LOGS="$PWD/logs"
PYTHON_BIN="${PYTHON_BIN:-}"
PORTA_BACKEND_ARQUIVO="$PASTA_BACKEND/porta.txt"

mkdir -p "$PASTA_LOGS"

if [ -z "$PYTHON_BIN" ]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="python3.11"
  else
    PYTHON_BIN="python3"
  fi
fi

api_respondendo() {
  curl -fsS --max-time 1 "$1/api/metricas" >/dev/null 2>&1
}

url_backend_existente() {
  if api_respondendo "http://127.0.0.1:5000"; then
    echo "http://127.0.0.1:5000"
    return 0
  fi

  if [ -f "$PORTA_BACKEND_ARQUIVO" ]; then
    local porta
    porta="$(tr -d '[:space:]' < "$PORTA_BACKEND_ARQUIVO")"
    if [ -n "$porta" ] && api_respondendo "http://127.0.0.1:$porta"; then
      echo "http://127.0.0.1:$porta"
      return 0
    fi
  fi

  return 1
}

echo "Verificando se o backend ja esta rodando..."
BACKEND_URL="$(url_backend_existente || true)"
if [ -n "$BACKEND_URL" ]; then
  echo "Backend ja estava rodando em $BACKEND_URL."
else
  echo "Iniciando o backend..."
  rm -f "$PORTA_BACKEND_ARQUIVO"
  (
    cd "$PASTA_BACKEND"
    nohup "$PYTHON_BIN" app.py > "$PASTA_LOGS/backend-saida.log" 2> "$PASTA_LOGS/backend-erro.log" < /dev/null &
  )

  for _ in $(seq 1 60); do
    BACKEND_URL="$(url_backend_existente || true)"
    if [ -n "$BACKEND_URL" ]; then
      break
    fi
    sleep 0.5
  done

  if [ -z "$BACKEND_URL" ]; then
    echo "Backend nao respondeu. Veja $PASTA_LOGS/backend-erro.log e $PASTA_LOGS/backend-saida.log." >&2
    exit 1
  fi
fi

echo "Backend em $BACKEND_URL"
echo "Verificando se a interface ja esta rodando..."
if curl -fsS --max-time 1 http://localhost:5173 >/dev/null 2>&1; then
  echo "Interface ja estava rodando. Se as chamadas /api falharem, reinicie a interface para usar $BACKEND_URL."
else
  echo "Iniciando a interface..."
  (
    cd "$PASTA_FRONTEND"
    VITE_API_PROXY_TARGET="$BACKEND_URL" nohup npm run dev > "$PASTA_LOGS/frontend-saida.log" 2> "$PASTA_LOGS/frontend-erro.log" < /dev/null &
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
