# -*- mode: python ; coding: utf-8 -*-
"""Build do backend empacotado do ProspectOS (PyInstaller, --onedir).

Uso:
    py -m PyInstaller prospectos.spec

Pré-requisitos na pasta backend/:
    - google-maps-scraper.exe (o binário do scraper)
    - node/node.exe (Node portátil, baixado do nodejs.org - alimenta o
      Playwright embutido no scraper)
    - ../frontend/dist buildado (npm run build)

Decisões:
    - onedir (não onefile): startup rápido, sem reextrair ~200MB a cada abertura,
      e é o formato que o instalador (Inno Setup) e o shell Electron esperam.
    - console configurável: PROSPECTOS_BUILD_CONSOLE=1 gera um .exe com console
      (útil pra depurar o bundle); o padrão é janela nenhuma (app "de verdade").
    - hiddenimports: keyring.backends.Windows é OBRIGATÓRIO - sem ele o keyring
      não acha o backend do Windows e as chaves de API cairiam em plaintext no
      banco. instagrapi é importado em runtime pelos .py do instagram (que vão
      como dados, fora da análise estática), então também precisa ser explícito.
"""

import os
from pathlib import Path

RAIZ = Path(SPECPATH)

datas = [
    # recursos read-only distribuídos com o app (lidos via paths.caminho_recurso)
    (str(RAIZ / "google-maps-scraper.exe"), "."),
    (str(RAIZ / "instagram" / "raspar_comentarios.py"), "instagram"),
    (str(RAIZ / "instagram" / "enriquecer_perfis.py"), "instagram"),
    (str(RAIZ / "instagram" / "login.py"), "instagram"),
    (str(RAIZ.parent / "frontend" / "dist"), "frontend_dist"),
    (str(RAIZ / "node" / "node.exe"), "node"),
]

a = Analysis(
    ["app.py"],
    pathex=[str(RAIZ)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "keyring.backends.Windows",
        "waitress",
        "instagrapi",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

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
    console=os.environ.get("PROSPECTOS_BUILD_CONSOLE") == "1",
    icon=str(RAIZ / "prospectos.ico") if (RAIZ / "prospectos.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ProspectOS",
)
