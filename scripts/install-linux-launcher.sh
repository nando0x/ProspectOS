#!/usr/bin/env bash
# Instala o ProspectOS no menu de aplicativos do Linux (~/.local/share/applications).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="$ROOT/scripts/prospectos-launch.sh"
ICON_SRC="$ROOT/backend/prospectos-icone-256.png"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
DESKTOP_FILE="$APP_DIR/prospectos.desktop"
ICON_DST="$ICON_DIR/prospectos.png"

usage() {
  echo "Uso: $0 [--uninstall]"
  echo "  (sem args)  instala atalho no menu de aplicativos"
  echo "  --uninstall remove o atalho e o ícone instalados"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f "$DESKTOP_FILE" "$ICON_DST"
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" 2>/dev/null || true
  fi
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" 2>/dev/null || true
  fi
  echo "ProspectOS removido do menu de aplicativos."
  exit 0
fi

if [[ ! -f "$LAUNCHER" ]]; then
  echo "Launcher não encontrado: $LAUNCHER" >&2
  exit 1
fi
if [[ ! -f "$ICON_SRC" ]]; then
  echo "Ícone não encontrado: $ICON_SRC" >&2
  exit 1
fi

chmod +x "$LAUNCHER" "$ROOT/scripts/install-linux-launcher.sh"

mkdir -p "$APP_DIR" "$ICON_DIR"
cp -f "$ICON_SRC" "$ICON_DST"

cat >"$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=ProspectOS
GenericName=CRM de prospecção
Comment=Prospecção de leads (Google Maps + Instagram) via Docker
Exec=$LAUNCHER
Icon=prospectos
Terminal=false
Categories=Office;
Keywords=CRM;leads;maps;instagram;prospeccao;
StartupNotify=true
EOF

chmod 644 "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" 2>/dev/null || true
fi

echo "Pronto. O ProspectOS deve aparecer no menu de aplicativos."
echo "  Atalho: $DESKTOP_FILE"
echo "  Ícone:  $ICON_DST"
echo
echo "Abra pelo menu ou rode: $LAUNCHER"
echo "Para remover: $0 --uninstall"
