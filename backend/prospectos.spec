# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform PyInstaller spec for ProspectOS backend sidecar.

Builds a native executable for the current platform using --onedir.
Supports darwin-arm64 (native Apple Silicon), win32-x64, and linux-x64.

Usage:
    pyinstaller backend/prospectos.spec --clean --noconfirm
    python -m PyInstaller backend/prospectos.spec --clean --noconfirm

Prerequisites:
    - frontend/dist/ (React build output, created by npm run build in frontend/)
    - shared/runtime-targets.json

Design decisions:
    - --onedir: faster startup, easier debugging, no re-extraction on each run.
      Better integration with Electron future sidecar loading.
    - Platform-conditional hidden imports: each OS gets only what it needs.
    - No scraper, Node, or Chromium bundled here: those are managed by the
      Playwright runtime manager or Electron packaging.
    - Console configurable via PROSPECTOS_BUILD_CONSOLE=1 for debugging.
"""

import os
import sys
from pathlib import Path

# ── platform detection ──────────────────────────────────────────────────────
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# ── paths derived from spec location ────────────────────────────────────────
SPEC_DIR = Path(SPECPATH).resolve()
REPO_ROOT = SPEC_DIR.parent

# ── console ─────────────────────────────────────────────────────────────────
console_enabled = os.environ.get("PROSPECTOS_BUILD_CONSOLE", "0") == "1"

# ── datas: files to bundle into _internal/ ──────────────────────────────────
datas = []

# Frontend build output — served by Flask when packaged
frontend_dist = REPO_ROOT / "frontend" / "dist"
if frontend_dist.is_dir():
    datas.append((str(frontend_dist), "frontend_dist"))
elif not os.environ.get("PROSPECTOS_BUILD_SKIP_FRONTEND_CHECK"):
    raise SystemExit(
        f"ERROR: frontend/dist not found at {frontend_dist}\n"
        "Run: cd frontend && npm ci && npm run build\n"
        "Or set PROSPECTOS_BUILD_SKIP_FRONTEND_CHECK=1 to skip this check."
    )

# Shared runtime manifest — tells the backend where to find scraper/node
shared_manifest = REPO_ROOT / "shared" / "runtime-targets.json"
if shared_manifest.is_file():
    datas.append((str(shared_manifest), "shared"))
else:
    raise SystemExit(f"ERROR: shared runtime manifest not found: {shared_manifest}")

# Instagram Python modules (imported dynamically by jobs)
for insta_module in ("login.py", "raspar_comentarios.py", "enriquecer_perfis.py"):
    p = SPEC_DIR / "instagram" / insta_module
    if p.is_file():
        datas.append((str(p), "instagram"))

# ── hidden imports ──────────────────────────────────────────────────────────
hiddenimports = [
    "waitress",
    "instagrapi",
    "instagrapi.exceptions",
    "fpdf",
    "ddgs",
]

# Keyring backends — platform-conditional
if IS_WINDOWS:
    hiddenimports.extend([
        "keyring.backends.Windows",
        "keyring.backends.WinVaultKeyring",
    ])
elif IS_MACOS:
    hiddenimports.extend([
        "keyring.backends.macOS",
    ])
elif IS_LINUX:
    hiddenimports.extend([
        "keyring.backends.SecretService",
    ])

# AI SDK hidden imports
hiddenimports.extend([
    "google",
    "google.genai",
    "openai",
])

# ── excludes ────────────────────────────────────────────────────────────────
excludes = [
    "pytest",
    "tkinter",
    "tcl",
    "tcl8",
    "idlelib",
]

# ── Analysis ────────────────────────────────────────────────────────────────
a = Analysis(
    ["app.py"],
    pathex=[str(SPEC_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# ── PYZ ─────────────────────────────────────────────────────────────────────
pyz = PYZ(a.pure)

# ── EXE ─────────────────────────────────────────────────────────────────────
icon_path = None
if IS_WINDOWS:
    win_icon = SPEC_DIR / "prospectos.ico"
    if win_icon.is_file():
        icon_path = str(win_icon)
elif IS_MACOS:
    mac_icon = SPEC_DIR / "prospectos-icone-256.png"
    if mac_icon.is_file():
        icon_path = str(mac_icon)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ProspectOS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=console_enabled,
    icon=icon_path,
)

# ── COLLECT (onedir) ────────────────────────────────────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ProspectOS",
)
