"""Build ProspectOS.app for darwin-arm64 — orchestrator.

Usage:
    python scripts/build_desktop.py [--clean] [--skip-frontend] [--skip-scraper]

Requires: Python 3, PyInstaller, Node/npm, Go, Xcode CLI.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
DESKTOP_DIR = REPO_ROOT / "desktop"
SHARED_DIR = REPO_ROOT / "shared"
SCRIPTS_DIR = REPO_ROOT / "scripts"

STAGING_DIR = DESKTOP_DIR / ".runtime-resources"
TARGET = "darwin-arm64"
STAGING_TARGET = STAGING_DIR / TARGET

IS_MACOS = sys.platform == "darwin"
PYTHON = os.environ.get("PROSPECTOS_PYTHON", sys.executable)


def _bail(msg: str):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _info(msg: str):
    print(f"  • {msg}")


def _ok(msg: str):
    print(f"  ✓ {msg}")


def _step(n: int, total: int, label: str):
    print(f"\n[{n}/{total}] {label}")
    print("-" * 50)


def _du(path: Path) -> str:
    if not path.exists():
        return "N/A"
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024:
            return f"{total:.1f}{unit}"
        total /= 1024
    return f"{total:.1f}TB"


def _run(cmd, cwd=None, **kwargs):
    _info(f"$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=str(cwd or REPO_ROOT), **kwargs)
    if result.returncode != 0:
        _bail(f"Comando falhou (exit={result.returncode})")
    return result


TOTAL_STEPS = 7


def validate_environment():
    _step(1, TOTAL_STEPS, "Validando ambiente")

    if not IS_MACOS:
        _bail("Este script requer macOS (darwin).")
    arch = os.uname().machine
    if arch != "arm64":
        _bail(f"Requer arm64, detectado: {arch}")
    _ok(f"Sistema: {sys.platform}-{arch}")

    try:
        import PyInstaller  # noqa: F401
        _info(f"PyInstaller: {__import__('PyInstaller').__version__}")
    except ImportError:
        _bail("PyInstaller nao instalado. pip install 'pyinstaller>=6.21,<7'")

    result = subprocess.run(["go", "version"], capture_output=True, text=True)
    if result.returncode != 0:
        _bail("Go nao encontrado. Instale com: brew install go")
    _info(f"Go: {result.stdout.strip()}")

    result = subprocess.run(["node", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        _bail("Node.js nao encontrado.")
    _info(f"Node: {result.stdout.strip()}")

    result = subprocess.run(
        ["xcrun", "--show-sdk-path"], capture_output=True, text=True
    )
    if result.returncode != 0:
        _info("  aviso: Xcode CLI pode nao estar instalado")
    else:
        _info(f"Xcode SDK: {result.stdout.strip()}")

    _ok("Ambiente OK")


def build_frontend():
    _step(2, TOTAL_STEPS, "Build do frontend")

    frontend_dist = FRONTEND_DIR / "dist"
    if frontend_dist.exists():
        _info(f"Removendo frontend/dist existente ({_du(frontend_dist)})")
        shutil.rmtree(frontend_dist)

    lockfile = FRONTEND_DIR / "package-lock.json"
    npm_cmd = "npm ci" if lockfile.exists() else "npm install"
    _info(f"Executando: {npm_cmd}")
    _run(npm_cmd.split(), cwd=FRONTEND_DIR)

    _info("Executando: npm run build")
    _run(["npm", "run", "build"], cwd=FRONTEND_DIR)

    if not frontend_dist.exists():
        _bail("npm run build concluido mas frontend/dist nao foi criado")
    _ok(f"Frontend pronto ({_du(frontend_dist)})")


def build_backend():
    _step(3, TOTAL_STEPS, "Build do backend PyInstaller")

    backend_dist = BACKEND_DIR / "dist"
    if backend_dist.exists():
        _info(f"Removendo backend/dist existente ({_du(backend_dist)})")
        shutil.rmtree(backend_dist)

    script = SCRIPTS_DIR / "build_backend.py"
    if not script.exists():
        _bail(f"Script de build do backend nao encontrado: {script}")

    _run([PYTHON, str(script), "--skip-frontend"], cwd=REPO_ROOT)

    bundle_dir = backend_dist / "ProspectOS"
    executable = bundle_dir / "ProspectOS"
    if not executable.exists():
        _bail(f"Executavel do backend nao encontrado: {executable}")

    result = subprocess.run(["file", str(executable)], capture_output=True, text=True)
    _info(f"file: {result.stdout.strip()}")

    result = subprocess.run(
        ["lipo", "-info", str(executable)], capture_output=True, text=True
    )
    _info(f"lipo: {result.stdout.strip()}")

    if "arm64" not in result.stdout:
        _bail(f"Backend nao e arm64:\n{result.stdout}")

    result = subprocess.run(
        ["otool", "-L", str(executable)], capture_output=True, text=True
    )
    for line in result.stdout.split("\n"):
        if "/opt/homebrew" in line or "/usr/local" in line:
            _info(f"  aviso: dependencia externa: {line.strip()}")

    _ok(f"Backend pronto: {_du(bundle_dir)}")


def build_scraper():
    _step(4, TOTAL_STEPS, "Build do scraper Go arm64")

    artifacts_file = SCRIPTS_DIR / "native-artifact-sources.json"
    if not artifacts_file.exists():
        _bail(f"Arquivo de fontes nao encontrado: {artifacts_file}")

    sources = json.loads(artifacts_file.read_text())
    scraper_cfg = sources.get("scraper", {})
    upstream = scraper_cfg.get("upstream", "gosom/google-maps-scraper")
    tag = scraper_cfg.get("tag", "v1.16.3")
    commit = scraper_cfg.get("commit", "")

    scraper_out = STAGING_TARGET / "scraper" / "google-maps-scraper"
    if scraper_out.exists():
        _info(f"Removendo scraper existente")
        scraper_out.unlink()

    STAGING_TARGET.mkdir(parents=True, exist_ok=True)

    temp_dir = REPO_ROOT / ".tmp-scraper-build"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    _info(f"Clonando {upstream} tag={tag}")
    _run(["git", "clone",
          f"https://github.com/{upstream}.git",
          str(temp_dir),
          "--depth", "1",
          "--branch", tag])

    if commit:
        _info(f"Verificando commit {commit}")
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=temp_dir,
            capture_output=True, text=True,
        )
        actual_commit = result.stdout.strip()
        if actual_commit != commit:
            _bail(f"Commit mismatch: esperado {commit}, obtido {actual_commit}")

    _info("Verificando modulos Go")
    _run(["go", "mod", "verify"], cwd=temp_dir)

    _info("Compilando scraper")
    scraper_dir = STAGING_TARGET / "scraper"
    scraper_dir.mkdir(parents=True, exist_ok=True)
    _run([
        "go", "build",
        "-trimpath",
        "-o", str(scraper_out),
        ".",
    ], cwd=temp_dir)

    if not scraper_out.exists():
        _bail(f"Scraper nao foi compilado: {scraper_out}")

    result = subprocess.run(["file", str(scraper_out)], capture_output=True, text=True)
    _info(f"file: {result.stdout.strip()}")

    result = subprocess.run(
        ["lipo", "-info", str(scraper_out)], capture_output=True, text=True
    )
    _info(f"lipo: {result.stdout.strip()}")

    if "arm64" not in result.stdout:
        _bail(f"Scraper nao e arm64:\n{result.stdout}")

    import hashlib
    sha = hashlib.sha256(scraper_out.read_bytes()).hexdigest()
    _info(f"SHA-256: {sha}")

    license_src = temp_dir / "LICENSE"
    if license_src.exists():
        shutil.copy2(license_src, scraper_dir / "LICENSE")
        _info("Licenca copiada")

    shutil.rmtree(temp_dir)

    scraper_out.chmod(0o755)
    _ok(f"Scraper pronto: {_du(scraper_dir)}")


def stage_resources():
    _step(5, TOTAL_STEPS, "Montando staging de recursos")

    if STAGING_DIR.exists():
        _info(f"Removendo staging existente ({_du(STAGING_DIR)})")
        shutil.rmtree(STAGING_DIR)

    STAGING_TARGET.mkdir(parents=True, exist_ok=True)

    shared_dest = STAGING_TARGET / "shared"
    shared_dest.mkdir(parents=True, exist_ok=True)
    for f in ["runtime-targets.json", "playwright-runtime-targets.json"]:
        src = SHARED_DIR / f
        if src.exists():
            shutil.copy2(src, shared_dest / f)
            _info(f"  shared/{f} copiado")

    scraper_src = STAGING_TARGET / "scraper" / "google-maps-scraper"
    if scraper_src.exists():
        _info(f"  scraper ja presente ({_du(scraper_src.parent)})")
    else:
        _info("  aviso: scraper ausente, sera necessario builda-lo antes")

    _info(f"Staging em: {STAGING_TARGET}")

    backend_dist = BACKEND_DIR / "dist"
    if backend_dist.exists():
        _ok(f"Backend dist presente ({_du(backend_dist)})")
    else:
        _info("  aviso: backend dist ausente")

    _ok("Staging montado")


def validate_staging():
    _step(6, TOTAL_STEPS, "Validando staging")

    required = [
        ("Manifesto runtime", SHARED_DIR / "runtime-targets.json"),
        ("Manifesto Playwright", SHARED_DIR / "playwright-runtime-targets.json"),
        ("Script build_backend", SCRIPTS_DIR / "build_backend.py"),
    ]

    if STAGING_TARGET.exists():
        required.extend([
            ("Scraper", STAGING_TARGET / "scraper" / "google-maps-scraper"),
            ("Manifesto shared", STAGING_TARGET / "shared" / "runtime-targets.json"),
            ("Manifesto Playwright shared", STAGING_TARGET / "shared" / "playwright-runtime-targets.json"),
        ])

    for label, p in required:
        if not p.exists():
            _info(f"  aviso: {label} ausente: {p}")
        else:
            _info(f"  {label}: {p}")

    backend_dist = BACKEND_DIR / "dist" / "ProspectOS"
    if backend_dist.exists():
        exe = backend_dist / "ProspectOS"
        if exe.exists():
            if not os.access(str(exe), os.X_OK):
                _bail(f"Backend sem permissao de execucao: {exe}")
            exe.chmod(0o755)
            _ok(f"Backend executavel: {exe}")
        _ok(f"Backend bundle: {backend_dist} ({_du(backend_dist)})")

    if STAGING_TARGET.exists():
        scraper = STAGING_TARGET / "scraper" / "google-maps-scraper"
        if scraper.exists():
            if not os.access(str(scraper), os.X_OK):
                _bail(f"Scraper sem permissao de execucao: {scraper}")
            scraper.chmod(0o755)
            _ok(f"Scraper executavel: {scraper}")

    _ok("Staging validado")


def build_electron():
    _step(7, TOTAL_STEPS, "Build Electron (electron-builder)")

    output_dir = DESKTOP_DIR / "saida"
    if output_dir.exists():
        _info(f"Removendo output existente ({_du(output_dir)})")
        shutil.rmtree(output_dir)

    if not (DESKTOP_DIR / "node_modules").exists():
        _info("node_modules ausente, executando npm ci")
        _run(["npm", "ci"], cwd=DESKTOP_DIR)

    _info("Configurando variaveis para build local (sem assinatura)")
    env = {**os.environ, "CSC_IDENTITY_AUTO_DISCOVERY": "false"}
    if "ELECTRON_BUILDER_ALLOW_UNRESOLVED_DEPENDENCIES" not in env:
        env["ELECTRON_BUILDER_ALLOW_UNRESOLVED_DEPENDENCIES"] = "1"

    _run(
        ["npx", "electron-builder", "--config", "electron-builder.yml",
         "--mac", "dir", "--arm64", "--publish", "never"],
        cwd=DESKTOP_DIR,
        env=env,
    )

    _ok("Electron build concluido")


def validate_app():
    _step(7, TOTAL_STEPS, "Validando .app") if False else None

    output_dir = DESKTOP_DIR / "saida"
    app_dirs = list(output_dir.glob("*.app"))
    if not app_dirs:
        _bail(f"Nenhum .app encontrado em {output_dir}")

    app_path = app_dirs[0]
    _info(f"Aplicativo: {app_path}")

    _run(["plutil", "-p", str(app_path / "Contents" / "Info.plist")])

    electron_bin = app_path / "Contents" / "MacOS" / "ProspectOS"
    _run(["file", str(electron_bin)])
    _run(["lipo", "-info", str(electron_bin)])

    checks = [
        ("Electron", electron_bin),
        ("Backend", app_path / "Contents" / "Resources" / "backend" / "ProspectOS"),
        ("Scraper", app_path / "Contents" / "Resources" / "scraper" / "google-maps-scraper"),
    ]

    for label, p in checks:
        if not p.exists():
            _bail(f"{label} nao encontrado em: {p}")
            continue
        result = subprocess.run(["file", str(p)], capture_output=True, text=True)
        _info(f"  {label}: {result.stdout.strip()}")
        result = subprocess.run(
            ["lipo", "-info", str(p)], capture_output=True, text=True
        )
        _info(f"    lipo: {result.stdout.strip()}")
        if not os.access(str(p), os.X_OK):
            _bail(f"{label} sem permissao de execucao")
        if "arm64" not in result.stdout:
            _bail(f"{label} nao e arm64")

    shared_manifest = app_path / "Contents" / "Resources" / "shared" / "runtime-targets.json"
    if not shared_manifest.exists():
        _bail(f"Manifesto compartilhado ausente: {shared_manifest}")

    result = subprocess.run(
        ["codesign", "-dv", "--verbose=4", str(app_path)],
        capture_output=True, text=True
    )
    _info(f"Assinatura:\n{result.stdout}\n{result.stderr}")

    total = sum(f.stat().st_size for f in app_path.rglob("*") if f.is_file())
    _info(f"Tamanho total: {_du(app_path)}")

    _ok(f"\n{'=' * 60}")
    _ok(f"  ProspectOS.app pronto!")
    _ok(f"  Path: {app_path}")
    _ok(f"  Tamanho: {_du(app_path)}")
    _ok(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(
        description="Build ProspectOS.app for darwin-arm64"
    )
    parser.add_argument("--clean", action="store_true", help="clean build dirs first")
    parser.add_argument("--skip-frontend", action="store_true", help="skip frontend build")
    parser.add_argument("--skip-scraper", action="store_true", help="skip scraper build")
    args = parser.parse_args()

    print("=" * 60)
    print("  ProspectOS — Desktop Build (darwin-arm64)")
    print("=" * 60)

    start = time.time()

    if args.clean:
        _info("Limpando diretorios de build...")
        for d in [BACKEND_DIR / "dist", BACKEND_DIR / "build",
                  FRONTEND_DIR / "dist", DESKTOP_DIR / "saida",
                  STAGING_DIR]:
            if d.exists():
                shutil.rmtree(d)
                _info(f"  removido: {d}")

    validate_environment()
    build_frontend()
    build_backend()

    if not args.skip_scraper:
        build_scraper()

    stage_resources()
    validate_staging()
    build_electron()
    validate_app()

    elapsed = time.time() - start
    print()
    print("-" * 60)
    print(f"  Build concluido em {elapsed:.0f}s")
    print("-" * 60)


if __name__ == "__main__":
    main()
