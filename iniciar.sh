#!/usr/bin/env bash
# Sobe o backend (Flask, porta 5000) e a interface (Vite, porta 5173) juntos.
# Equivalente Linux/macOS do iniciar.bat. Uso: ./iniciar.sh
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASTA_BACKEND="$RAIZ/backend"
PASTA_FRONTEND="$RAIZ/frontend"
PASTA_LOGS="$RAIZ/logs"

mkdir -p "$PASTA_LOGS"

# python do venv se existir, senão o python3 do sistema
if [ -x "$PASTA_BACKEND/.venv/bin/python" ]; then
    PYTHON="$PASTA_BACKEND/.venv/bin/python"
else
    PYTHON="python3"
fi

esta_no_ar() {
    curl -s -o /dev/null --max-time 1 "$1" 2>/dev/null
}

echo "Verificando se o backend já está rodando..."
if esta_no_ar "http://127.0.0.1:5000/api/metricas"; then
    echo "Backend já estava rodando."
else
    echo "Iniciando o backend..."
    ( cd "$PASTA_BACKEND" && nohup "$PYTHON" app.py \
        >"$PASTA_LOGS/backend-saida.log" 2>"$PASTA_LOGS/backend-erro.log" & )
fi

echo "Verificando se a interface já está rodando..."
if esta_no_ar "http://localhost:5173"; then
    echo "Interface já estava rodando."
else
    echo "Iniciando a interface..."
    ( cd "$PASTA_FRONTEND" && nohup npm run dev \
        >"$PASTA_LOGS/frontend-saida.log" 2>"$PASTA_LOGS/frontend-erro.log" & )
    sleep 4
fi

URL="http://localhost:5173"
echo "Abrindo $URL ..."
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1 || true
else
    echo "Abra manualmente no navegador: $URL"
fi
