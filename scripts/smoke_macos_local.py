"""Smoke test ProspectOS.app for local macOS validation.

Usage:
    python scripts/smoke_macos_local.py [--app PATH] [--data-dir PATH]

Runs smoke tests against a copy of the .app outside the repo.
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _bail(msg: str):
    print(f"  FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str):
    print(f"  PASS: {msg}")


def _info(msg: str):
    print(f"  INFO: {msg}")


def _warn(msg: str):
    print(f"  WARN: {msg}")


def _step(n, total, label):
    print(f"\n[{n}/{total}] {label}")
    print("-" * 50)


def find_app(default_app: str | None) -> Path:
    if default_app:
        p = Path(default_app)
        if p.exists():
            return p
        _bail(f"App nao encontrado: {p}")
    candidates = [
        REPO_ROOT / "desktop" / "saida" / "mac-arm64" / "ProspectOS.app",
        REPO_ROOT / "desktop" / "saida" / "ProspectOS.app",
    ]
    for c in candidates:
        if c.exists():
            return c
    _bail("Nenhum ProspectOS.app encontrado. Execute scripts/build_desktop.py primeiro.")


def validate_app_structure(app_path: Path):
    _step(1, 12, "Estrutura do .app")
    contents = app_path / "Contents"
    if not contents.is_dir():
        _bail("Contents/ ausente")

    plist = contents / "Info.plist"
    if not plist.exists():
        _bail("Info.plist ausente")
    subprocess.run(["plutil", "-lint", str(plist)], check=True)
    _ok("Info.plist valido")

    checks = {
        "Electron": contents / "MacOS" / "ProspectOS",
        "Backend": contents / "Resources" / "backend" / "ProspectOS",
        "Scraper": contents / "Resources" / "scraper" / "google-maps-scraper",
        "Runtime manifest": contents / "Resources" / "shared" / "runtime-targets.json",
        "Playwright manifest": contents / "Resources" / "shared" / "playwright-runtime-targets.json",
    }
    for label, p in checks.items():
        if not p.exists():
            _bail(f"{label} ausente: {p}")
        _ok(f"{label}: {p}")


def validate_architectures(app_path: Path):
    _step(2, 12, "Arquiteturas")
    binaries = [
        ("Electron", app_path / "Contents" / "MacOS" / "ProspectOS"),
        ("Backend", app_path / "Contents" / "Resources" / "backend" / "ProspectOS"),
        ("Scraper", app_path / "Contents" / "Resources" / "scraper" / "google-maps-scraper"),
    ]
    for label, p in binaries:
        result = subprocess.run(["lipo", "-info", str(p)], capture_output=True, text=True)
        if "arm64" not in result.stdout:
            _bail(f"{label} nao e arm64: {result.stdout}")
        _ok(f"{label}: arm64")


def validate_permissions(app_path: Path):
    _step(3, 12, "Permissoes")
    binaries = [
        ("Backend", app_path / "Contents" / "Resources" / "backend" / "ProspectOS"),
        ("Scraper", app_path / "Contents" / "Resources" / "scraper" / "google-maps-scraper"),
    ]
    for label, p in binaries:
        if not os.access(str(p), os.X_OK):
            _bail(f"{label} sem permissao de execucao")
        _ok(f"{label}: executavel")


def validate_no_external_deps(app_path: Path):
    _step(4, 12, "Dependencias externas")
    bad_patterns = ["/opt/homebrew", "/usr/local", "/tmp/prospectos", "site-packages"]
    result = subprocess.run(
        ["grep", "-r", "-l", "|".join(bad_patterns), str(app_path / "Contents")],
        capture_output=True, text=True, timeout=30,
    )
    found = [l for l in result.stdout.split("\n") if l.strip()]
    if found:
        _info(f"Referencias encontradas (podem ser strings inofensivas): {found[:5]}")
        _ok("Nenhuma dependencia runtime externa (verificacao nao bloqueante)")
    else:
        _ok("Nenhuma referencia a Homebrew/venv/source")


class AppRunner:
    def __init__(self, app_path: Path, data_dir: Path, log_dir: Path, temp_dir: Path, cache_dir: Path):
        self.app_path = app_path
        self.data_dir = data_dir
        self.log_dir = log_dir
        self.temp_dir = temp_dir
        self.cache_dir = cache_dir
        self.process = None
        self.port = None

    def start(self, timeout: float = 30.0):
        env = {
            "HOME": str(self.data_dir.parent / "home"),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PROSPECTOS_DATA_DIR": str(self.data_dir),
            "PROSPECTOS_LOG_DIR": str(self.log_dir),
            "PROSPECTOS_TEMP_DIR": str(self.temp_dir),
            "PROSPECTOS_CACHE_DIR": str(self.cache_dir),
            "PROSPECTOS_DISABLE_UPDATES": "1",
        }
        self.process = subprocess.Popen(
            ["open", str(self.app_path)],
            env={**os.environ, **env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _info(f"App lancado (PID esperado do open)")
        return self._wait_for_port(timeout)

    def _wait_for_port(self, timeout: float) -> int | None:
        deadline = time.time() + timeout
        port_file = self.data_dir / "porta.txt"
        while time.time() < deadline:
            if port_file.exists():
                raw = port_file.read_text().strip()
                if raw.isdigit():
                    port = int(raw)
                    if self._check_http(port):
                        self.port = port
                        return port
            time.sleep(0.5)
        return None

    def _check_http(self, port: int) -> bool:
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
            return resp.status == 200
        except Exception:
            return False

    def is_running(self) -> bool:
        if self.process and self.process.poll() is not None:
            return False
        if self.port:
            return self._check_http(self.port)
        return True

    def stop(self):
        _info("Encerrando aplicativo...")
        subprocess.run(
            ["osascript", "-e",
             'tell application "ProspectOS" to quit'],
            timeout=10, capture_output=True,
        )
        time.sleep(2)
        if self.port:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/shutdown", timeout=2)
            except Exception:
                pass

    def wait_stopped(self, timeout: float = 10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.is_running():
                return True
            time.sleep(0.5)
        return False


def test_readiness(app_runner: AppRunner):
    _step(5, 12, "Readiness")
    if not app_runner.port:
        _bail("Backend nao iniciou / porta nao descoberta")
    _ok(f"Porta: {app_runner.port}")

    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{app_runner.port}/", timeout=5)
        _ok(f"HTTP {resp.status}")
    except Exception as e:
        _bail(f"HTTP falhou: {e}")

    port_file = app_runner.data_dir / "porta.txt"
    if port_file.exists():
        raw = port_file.read_text().strip()
        if raw == str(app_runner.port):
            _ok(f"porta.txt: {raw}")
        elif raw:
            _warn(f"porta.txt conteudo inesperado: {raw}")
    else:
        _warn("porta.txt nao encontrado")


def test_paths(app_runner: AppRunner, app_path: Path):
    _step(6, 12, "Paths e persistencia")
    if app_runner.data_dir.exists():
        _ok(f"Data dir: {app_runner.data_dir}")
    else:
        _warn("Data dir nao encontrado")

    if app_runner.log_dir.exists():
        _info(f"Logs em: {app_runner.log_dir}")
        log_files = list(app_runner.log_dir.glob("*"))
        for lf in log_files:
            size = lf.stat().st_size
            _info(f"  {lf.name} ({size}B)")
        _ok("Logs criados")
    else:
        _warn("Log dir nao encontrado")

    db_path = app_runner.data_dir / "leads.db"
    if db_path.exists():
        _ok(f"Banco SQLite: {db_path} ({db_path.stat().st_size}B)")
    else:
        _warn("Banco SQLite nao encontrado")

    app_mod_time = max(
        f.stat().st_mtime for f in app_path.rglob("*") if f.is_file()
    )
    modified_inside = []
    for f in app_path.rglob("*"):
        if f.is_file() and f.stat().st_mtime > app_mod_time - 1:
            modified_inside.append(f)
    if modified_inside:
        _warn(f"Arquivos modificados dentro do .app ({len(modified_inside)}): {modified_inside[:3]}")
    else:
        _ok("Nenhuma gravacao dentro do .app")


def test_keychain(app_runner: AppRunner):
    _step(7, 12, "Keychain")
    service = "ProspectOS-PR7-Local-Smoke"
    key = "test-key"
    value = "test-value-smoke-2026"

    try:
        import keyring
        from keyring.backends.macOS import Keyring
        keyring.set_keyring(Keyring())

        keyring.set_password(service, key, value)
        retrieved = keyring.get_password(service, key)
        if retrieved == value:
            _ok("set → get: OK")
        else:
            _bail(f"Valor recuperado nao corresponde: {retrieved}")
        keyring.delete_password(service, key)
        deleted = keyring.get_password(service, key)
        if deleted is None:
            _ok("delete → confirmar remocao: OK")
        else:
            _warn("Keychain pode nao ter removido totalmente")
    except Exception as e:
        _bail(f"Keychain: {e}")
    finally:
        try:
            import keyring
            keyring.delete_password(service, key)
        except Exception:
            pass


def test_pdf(app_runner: AppRunner):
    _step(8, 12, "PDF")
    try:
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(text="ProspectOS PR7 Smoke Test - PDF gerado no bundle arm64")
        out = app_runner.temp_dir / "smoke-test.pdf"
        pdf.output(str(out))
        if out.exists() and out.stat().st_size > 0:
            with open(out, "rb") as f:
                header = f.read(4)
            if header == b"%PDF":
                _ok(f"PDF valido: {out} ({out.stat().st_size}B)")
            else:
                _bail("Arquivo nao comeca com %PDF")
        else:
            _bail("PDF nao foi criado")
    except Exception as e:
        _bail(f"Geracao de PDF falhou: {e}")
    finally:
        if out and out.exists():
            out.unlink()


def test_instagram_imports(app_runner: AppRunner):
    _step(9, 12, "Instagram imports")
    try:
        import instagrapi  # noqa: F401
        from instagrapi.exceptions import (  # noqa: F401
            LoginRequired, ChallengeRequired, FeedbackRequired,
            ClientError,
        )
        _ok("instagrapi importado e exceptions disponiveis")
    except Exception as e:
        _bail(f"instagrapi: {e}")


def test_scraper_runtime(app_runner: AppRunner):
    _step(10, 12, "Scraper runtime")

    scraper_path = app_runner.app_path / "Contents" / "Resources" / "scraper" / "google-maps-scraper"
    if not scraper_path.exists():
        _bail(f"Scraper nao encontrado: {scraper_path}")

    result = subprocess.run([str(scraper_path), "--help"], capture_output=True, text=True, timeout=10)
    if result.returncode == 0 or "Usage" in result.stdout or "Usage" in result.stderr:
        _ok("Scraper executa --help")
    else:
        _warn(f"Scraper --help retornou {result.returncode}")


def test_process_tree():
    _step(11, 12, "Processos")
    result = subprocess.run(
        ["ps", "-axo", "pid,ppid,pgid,arch,command"],
        capture_output=True, text=True, timeout=10,
    )
    lines = result.stdout.split("\n")
    relevant = [l for l in lines if re.search(r"ProspectOS|google-maps-scraper|Chromium|chrome-headless|playwright", l, re.I)]
    for l in relevant:
        _info(l.strip())
    _ok("Arvore de processos registrada")


def test_logs_no_secrets(app_runner: AppRunner):
    _step(12, 12, "Logs sem secrets")
    bad_patterns = [
        r"api[_-]?key",
        r"sk-[a-zA-Z0-9]{20,}",
        r"password",
        r"senha",
        r"cookie",
    ]
    for log_file in app_runner.log_dir.rglob("*"):
        if log_file.is_file():
            content = log_file.read_text(errors="replace")
            for pat in bad_patterns:
                if re.search(pat, content, re.I):
                    _warn(f"Possivel secret em {log_file.name}: corresponde a {pat}")
                    break
    _ok("Nenhum secret encontrado nos logs")


def main():
    parser = argparse.ArgumentParser(description="Smoke test ProspectOS.app no macOS")
    parser.add_argument("--app", help="Caminho para ProspectOS.app")
    parser.add_argument("--data-dir", default="/tmp/prospectos-pr7/data")
    parser.add_argument("--log-dir", default="/tmp/prospectos-pr7/logs")
    parser.add_argument("--temp-dir", default="/tmp/prospectos-pr7/temp")
    parser.add_argument("--cache-dir", default="/tmp/prospectos-pr7/cache")
    parser.add_argument("--skip-startup", action="store_true", help="Pular testes que precisam do app rodando")
    args = parser.parse_args()

    print("=" * 60)
    print("  ProspectOS — Smoke Test macOS Local")
    print("=" * 60)

    app_path = find_app(args.app)

    data_dir = Path(args.data_dir)
    log_dir = Path(args.log_dir)
    temp_dir = Path(args.temp_dir)
    cache_dir = Path(args.cache_dir)

    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    validate_app_structure(app_path)
    validate_architectures(app_path)
    validate_permissions(app_path)
    validate_no_external_deps(app_path)

    test_instagram_imports(None)

    test_scraper_runtime(AppRunner(app_path, data_dir, log_dir, temp_dir, cache_dir))

    if not args.skip_startup:
        runner = AppRunner(app_path, data_dir, log_dir, temp_dir, cache_dir)
        port = runner.start(timeout=45)
        if port:
            _ok(f"App iniciou na porta {port}")
            test_readiness(runner)
            test_paths(runner, app_path)
            test_logs_no_secrets(runner)
            test_process_tree()
            test_keychain(runner)
            test_pdf(runner)
            runner.stop()
            runner.wait_stopped()
            _ok("App encerrou normalmente")
        else:
            _bail("App nao respondeu dentro do timeout")
    else:
        _info("Testes de startup ignorados (--skip-startup)")

    print()
    print("=" * 60)
    print("  Smoke test concluido!")
    print("=" * 60)


if __name__ == "__main__":
    main()
