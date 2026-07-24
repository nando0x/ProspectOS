# syntax=docker/dockerfile:1

FROM node:20-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PROSPECTOS_DATA_DIR=/data \
    PROSPECTOS_HOST=0.0.0.0 \
    PROSPECTOS_PORT=5000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Dependências do Chromium/Playwright usadas pelo scraper
RUN npx --yes playwright@1.49.1 install-deps chromium

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY scripts/ /app/scripts/
RUN chmod +x /app/scripts/baixar-scraper.sh
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000
VOLUME ["/data"]

ENTRYPOINT ["/entrypoint.sh"]
