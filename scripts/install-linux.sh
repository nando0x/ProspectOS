#!/usr/bin/env bash
# Instalador one-click do ProspectOS no Linux (Docker Compose + atalho no menu).
set -euo pipefail

PROSPECTOS_HOME="${PROSPECTOS_HOME:-$HOME/ProspectOS}"
PROSPECTOS_REPO="${PROSPECTOS_REPO:-https://github.com/Teolfeu/ProspectOS.git}"
PROSPECTOS_BRANCH="${PROSPECTOS_BRANCH:-linux-docker}"
PROSPECTOS_IMAGE="${PROSPECTOS_IMAGE:-ghcr.io/teolfeu/prospectos:latest}"
PROSPECTOS_TARBALL_URL="${PROSPECTOS_TARBALL_URL:-}"
PROSPECTOS_URL="${PROSPECTOS_URL:-http://127.0.0.1:5000}"
HEALTH_URL="$PROSPECTOS_URL/api/metricas"

NO_START=0

usage() {
  cat <<EOF
Uso: $0 [opções]

Instala o ProspectOS no Linux: clona o repositório, configura Docker Compose,
sobe o container, instala atalho no menu e abre o navegador.

Variáveis de ambiente:
  PROSPECTOS_HOME       Diretório de instalação (padrão: ~/ProspectOS)
  PROSPECTOS_REPO       URL do repositório git (padrão: Teolfeu/ProspectOS)
  PROSPECTOS_BRANCH     Branch a usar (padrão: linux-docker)
  PROSPECTOS_IMAGE      Imagem Docker pré-construída (padrão: ghcr.io/teolfeu/prospectos:latest)
  PROSPECTOS_TARBALL_URL  URL de tarball em vez de git clone (opcional)

Opções:
  --no-start            Instala/clona/atalho sem subir o Docker
  --uninstall-launcher  Remove o atalho do menu de aplicativos
  -h, --help            Mostra esta ajuda

Exemplos:
  curl -fsSL .../install-linux.sh | bash
  PROSPECTOS_HOME=~/apps/ProspectOS $0
  $0 --no-start
EOF
}

info()  { echo "▸ $*"; }
warn()  { echo "⚠ $*" >&2; }
erro()  { echo "✗ $*" >&2; exit 1; }

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --no-start) NO_START=1; shift ;;
      --uninstall-launcher)
        helper="${PROSPECTOS_HOME}/scripts/install-linux-launcher.sh"
        if [[ ! -f "$helper" ]]; then
          helper="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install-linux-launcher.sh"
        fi
        [[ -f "$helper" ]] || erro "Não achei install-linux-launcher.sh. Defina PROSPECTOS_HOME ou rode a partir do repositório."
        exec "$helper" --uninstall
        ;;
      -h|--help) usage; exit 0 ;;
      *) erro "Opção desconhecida: $1 (use --help)" ;;
    esac
  done
}

verificar_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    erro "Docker não encontrado. Instale o Docker Engine + Compose v2 e tente de novo.
  https://docs.docker.com/engine/install/"
  fi
  if ! docker info >/dev/null 2>&1; then
    erro "O Docker está instalado, mas o daemon não está rodando.
  Inicie o serviço (ex.: sudo systemctl start docker) e tente de novo."
  fi
  if ! docker compose version >/dev/null 2>&1; then
    erro "Docker Compose v2 não encontrado. Instale o plugin 'docker compose' e tente de novo."
  fi
}

obter_codigo() {
  if [[ -n "$PROSPECTOS_TARBALL_URL" ]]; then
    info "Baixando código de $PROSPECTOS_TARBALL_URL …"
    local tmp
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' RETURN
    curl -fsSL "$PROSPECTOS_TARBALL_URL" -o "$tmp/prospectos.tar.gz"
    mkdir -p "$PROSPECTOS_HOME"
    tar -xzf "$tmp/prospectos.tar.gz" -C "$tmp"
    # Suporta tarball com pasta raiz ou arquivos soltos
    local extracted
    extracted="$(find "$tmp" -mindepth 1 -maxdepth 1 ! -name 'prospectos.tar.gz' -type d | head -1)"
    if [[ -z "$extracted" ]]; then
      erro "Não foi possível extrair o tarball em $PROSPECTOS_TARBALL_URL"
    fi
    rsync -a --delete "$extracted/" "$PROSPECTOS_HOME/"
    return
  fi

  if ! command -v git >/dev/null 2>&1; then
    erro "Git não encontrado. Instale git ou defina PROSPECTOS_TARBALL_URL com um tarball de release."
  fi

  if [[ -d "$PROSPECTOS_HOME/.git" ]]; then
    info "Atualizando repositório em $PROSPECTOS_HOME …"
    if [[ -n "$(git -C "$PROSPECTOS_HOME" status --porcelain 2>/dev/null)" ]]; then
      warn "O diretório tem alterações locais não commitadas; o pull pode falhar."
    fi
    git -C "$PROSPECTOS_HOME" fetch origin "$PROSPECTOS_BRANCH"
    git -C "$PROSPECTOS_HOME" checkout "$PROSPECTOS_BRANCH"
    git -C "$PROSPECTOS_HOME" pull --ff-only origin "$PROSPECTOS_BRANCH" || \
      warn "Pull fast-forward falhou — usando a cópia local atual."
  elif [[ -d "$PROSPECTOS_HOME" ]]; then
    erro "$PROSPECTOS_HOME já existe mas não é um repositório git.
  Mova ou remova o diretório, ou defina PROSPECTOS_HOME para outro caminho."
  else
    info "Clonando $PROSPECTOS_REPO (branch $PROSPECTOS_BRANCH) em $PROSPECTOS_HOME …"
    git clone --branch "$PROSPECTOS_BRANCH" --depth 1 "$PROSPECTOS_REPO" "$PROSPECTOS_HOME"
  fi
}

configurar_env() {
  local env_file="$PROSPECTOS_HOME/.env"
  if [[ ! -f "$env_file" ]]; then
    if [[ -f "$PROSPECTOS_HOME/backend/.env.example" ]]; then
      cp "$PROSPECTOS_HOME/backend/.env.example" "$env_file"
      echo
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
      echo "  IMPORTANTE: edite $env_file"
      echo "  Cole ao menos uma chave de IA (Gemini, Groq ou NVIDIA)"
      echo "  para gerar mensagens de abordagem."
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
      echo
    else
      warn "backend/.env.example não encontrado; crie $env_file manualmente."
    fi
  fi

  # Garante PROSPECTOS_IMAGE no .env (comentado se ausente)
  if [[ -f "$env_file" ]] && ! grep -q '^PROSPECTOS_IMAGE=' "$env_file" 2>/dev/null; then
    {
      echo ""
      echo "# Imagem Docker pré-construída (opcional; compose faz build local se ausente)"
      echo "# PROSPECTOS_IMAGE=$PROSPECTOS_IMAGE"
    } >>"$env_file"
  fi
}

subir_docker() {
  info "Preparando containers Docker …"
  cd "$PROSPECTOS_HOME"
  export PROSPECTOS_IMAGE

  # Tenta puxar imagem pré-construída; ignora falha (build local como fallback)
  docker compose pull 2>/dev/null || true

  docker compose up -d --build || erro "Falha ao iniciar o ProspectOS. Veja: docker compose logs"
}

aguardar_api() {
  info "Aguardando a API responder em $HEALTH_URL (até ~3 min) …"
  for _ in $(seq 1 90); do
    if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  erro "O container subiu, mas a API não respondeu a tempo.
  Confira: cd $PROSPECTOS_HOME && docker compose logs -f"
}

abrir_navegador() {
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$PROSPECTOS_URL" >/dev/null 2>&1 || true
  elif command -v sensible-browser >/dev/null 2>&1; then
    sensible-browser "$PROSPECTOS_URL" >/dev/null 2>&1 || true
  else
    info "Abra manualmente: $PROSPECTOS_URL"
  fi
}

instalar_atalho() {
  chmod +x "$PROSPECTOS_HOME/scripts/prospectos-launch.sh" \
            "$PROSPECTOS_HOME/scripts/install-linux-launcher.sh" \
            "$PROSPECTOS_HOME/scripts/install-linux.sh" 2>/dev/null || true
  "$PROSPECTOS_HOME/scripts/install-linux-launcher.sh"
}

resumo_sucesso() {
  cat <<EOF

╔══════════════════════════════════════════════════════════════╗
║  ProspectOS instalado com sucesso!                           ║
╚══════════════════════════════════════════════════════════════╝

  URL:      $PROSPECTOS_URL
  Pasta:    $PROSPECTOS_HOME
  Dados:    volume Docker prospectos-data

  Próximos passos:
    1. Edite $PROSPECTOS_HOME/.env (chaves de IA)
    2. Abra pelo menu de aplicativos ou acesse a URL acima

  Atualizar:
    $0
    # ou: cd $PROSPECTOS_HOME && git pull && docker compose up -d --build

  Remover atalho do menu:
    $0 --uninstall-launcher

  Parar os containers:
    cd $PROSPECTOS_HOME && docker compose down

EOF
}

main() {
  parse_args "$@"

  echo
  echo "ProspectOS — instalador Linux"
  echo "─────────────────────────────"
  echo

  verificar_docker
  obter_codigo
  configurar_env

  if [[ "$NO_START" -eq 1 ]]; then
    instalar_atalho
    info "Instalação concluída (--no-start: containers não foram iniciados)."
    echo "  Para subir: cd $PROSPECTOS_HOME && docker compose up -d --build"
    exit 0
  fi

  subir_docker
  aguardar_api
  instalar_atalho
  abrir_navegador
  resumo_sucesso
}

main "$@"
