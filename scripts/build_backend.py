"""Build the ProspectOS backend sidecar with PyInstaller.

Usage:
    python scripts/build_backend.py
    python scripts/build_backend.py --clean
    python scripts/build_backend.py --skip-frontend
    python scripts/build_backend.py --dist-dir /tmp/prospectos-dist
    python scripts/build_backend.py --work-dir /tmp/prospectos-build
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
SPEC_FILE = BACKEND_DIR / "prospectos.spec"

IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

KNOWN_DIST_DIRS = ["backend/dist", "backend/build"]


def _bail(msg: str):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _info(msg: str):
    print(f"  • {msg}")


def validate_environment():
    _info("validando ambiente...")
    if not SPEC_FILE.exists():
        _bail(f"spec nao encontrado: {SPEC_FILE}")

    if IS_MACOS:
        arch = os.uname().machine
        if arch != "arm64":
            _bail(f"build nativo requer arm64, detectado: {arch}")
        _info(f"arquitetura: {arch}")

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        _bail("PyInstaller nao instalado. Execute: pip install pyinstaller>=6.21,<7")

    _info(f"PyInstaller: {__import__('PyInstaller').__version__}")


def validate_frontend(skip_frontend: bool):
    frontend_dist = FRONTEND_DIR / "dist"
    if not frontend_dist.exists():
        if skip_frontend:
            _info("frontend/dist ausente, --skip-frontend ativo — continuando")
            return False
        _bail(
            f"frontend/dist nao encontrado em {frontend_dist}. "
            "Execute 'npm ci && npm run build' no diretorio frontend/ "
            "ou use --skip-frontend para desenvolvimento."
        )
    _info(f"frontend/dist encontrado ({_du(frontend_dist)})")
    return True


def build_frontend():
    _info("buildando frontend React...")
    if not (FRONTEND_DIR / "package.json").exists():
        _bail(f"frontend/package.json nao encontrado em {FRONTEND_DIR}")

    lockfile = FRONTEND_DIR / "package-lock.json"
    npm_cmd = "npm ci" if lockfile.exists() else "npm install"

    _info(f"executando: {npm_cmd}")
    subprocess.run(
        npm_cmd.split(),
        cwd=str(FRONTEND_DIR),
        check=True,
    )

    _info("executando: npm run build")
    subprocess.run(
        ["npm", "run", "build"],
        cwd=str(FRONTEND_DIR),
        check=True,
    )

    frontend_dist = FRONTEND_DIR / "dist"
    if not frontend_dist.exists():
        _bail("npm run build concluido mas frontend/dist nao foi criado")
    _info(f"frontend/dist criado ({_du(frontend_dist)})")


def clean_build_dirs():
    _info("limpando diretorios de build...")
    for d in KNOWN_DIST_DIRS:
        p = REPO_ROOT / d
        if p.exists():
            shutil.rmtree(p)
            _info(f"  removido: {d}")


def run_pyinstaller(work_dir: str | None, dist_dir: str | None):
    _info("executando PyInstaller...")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(SPEC_FILE),
    ]

    if work_dir:
        cmd.extend(["--workpath", work_dir])
    if dist_dir:
        cmd.extend(["--distpath", dist_dir])

    _info(f"comando: {' '.join(cmd)}")
    start = time.time()

    result = subprocess.run(cmd, cwd=str(BACKEND_DIR))
    elapsed = time.time() - start

    if result.returncode != 0:
        _bail(f"PyInstaller falhou (exit={result.returncode})")

    _info(f"PyInstaller concluido em {elapsed:.1f}s")
    return elapsed


def validate_output(dist_dir: str | None):
    _info("validando output do PyInstaller...")

    dist_base = Path(dist_dir) if dist_dir else (BACKEND_DIR / "dist")
    bundle_dir = dist_base / "ProspectOS"

    if not bundle_dir.exists():
        _bail(f"bundle nao encontrado: {bundle_dir}")

    executable = bundle_dir / "ProspectOS"
    if IS_WINDOWS:
        executable = bundle_dir / "ProspectOS.exe"

    if not executable.exists():
        _bail(f"executavel nao encontrado: {executable}")

    _info(f"executavel: {executable}")

    if IS_MACOS:
        result = subprocess.run(
            ["file", str(executable)], capture_output=True, text=True
        )
        _info(f"file: {result.stdout.strip()}")

        result_lipo = subprocess.run(
            ["lipo", "-info", str(executable)], capture_output=True, text=True
        )
        _info(f"lipo: {result_lipo.stdout.strip()}")

    _info(f"tamanho: {_du(bundle_dir)}")
    n_files = sum(1 for _ in bundle_dir.rglob("*") if _.is_file())
    _info(f"arquivos: {n_files}")

    return bundle_dir, executable


def _du(path: Path) -> str:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024:
            return f"{total:.1f}{unit}"
        total /= 1024
    return f"{total:.1f}TB"


def main():
    parser = argparse.ArgumentParser(
        description="Build the ProspectOS backend sidecar with PyInstaller"
    )
    parser.add_argument("--clean", action="store_true", help="clean build dirs first")
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="skip frontend build (use existing frontend/dist)",
    )
    parser.add_argument(
        "--dist-dir",
        default=None,
        help="custom dist directory (default: backend/dist)",
    )
    parser.add_argument(
        "--work-dir",
        default=None,
        help="custom work directory (default: PyInstaller default)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  ProspectOS — Backend PyInstaller Build")
    print("=" * 60)

    validate_environment()

    has_frontend = validate_frontend(args.skip_frontend)

    if not has_frontend and not args.skip_frontend:
        build_frontend()
    elif not has_frontend and args.skip_frontend:
        _info("skipping frontend build (--skip-frontend)")
    else:
        _info("frontend/dist ja existe")

    if args.clean:
        clean_build_dirs()

    elapsed = run_pyinstaller(args.work_dir, args.dist_dir)

    bundle_dir, executable = validate_output(args.dist_dir)

    print()
    print("-" * 60)
    print(f"  Build concluido com sucesso!")
    print(f"  Bundle:     {bundle_dir}")
    print(f"  Executavel: {executable}")
    print(f"  Tamanho:    {_du(bundle_dir)}")
    print(f"  Duracao:    {elapsed:.1f}s")
    print("-" * 60)


if __name__ == "__main__":
    main()
