"""Validation utilities for Playwright runtime components."""

import hashlib
import json
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_file_exists(path: Path, label: str = "Arquivo") -> bool:
    if not path.exists():
        logger.error("%s nao encontrado: %s", label, path)
        return False
    return True


def validate_is_file(path: Path, label: str = "Arquivo") -> bool:
    if not validate_file_exists(path, label):
        return False
    if path.is_dir():
        logger.error("%s e um diretorio: %s", label, path)
        return False
    return True


def validate_is_executable(path: Path, label: str = "Executavel") -> bool:
    if not validate_is_file(path, label):
        return False
    if sys.platform != "win32":
        st = path.stat()
        if not (st.st_mode & stat.S_IXUSR):
            logger.error("%s nao tem permissao de execucao: %s", label, path)
            return False
    return True


def validate_sha256(path: Path, expected: str) -> bool:
    if not path.exists():
        return False
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected:
        logger.error("SHA-256 mismatch para %s: esperado=%s atual=%s", path.name, expected, actual)
        return False
    return True


def run_subprocess(cmd, cwd=None, env=None, timeout=30):
    """Run a subprocess and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except FileNotFoundError:
        return -2, "", "COMMAND_NOT_FOUND"
    except Exception as e:
        return -3, "", str(e)


def check_architecture(path: Path, expected_arch: str = "arm64") -> tuple[bool, str]:
    """Check binary architecture using `file` command (macOS/Linux)."""
    if sys.platform == "win32":
        return True, ""
    if not path.exists():
        return False, "arquivo nao existe"
    try:
        result = subprocess.run(
            ["file", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout.lower()
        if expected_arch == "arm64":
            if "arm64" in output or "aarch64" in output:
                return True, output.strip()
            return False, f"arquitetura nao e {expected_arch}: {output.strip()}"
        if expected_arch == "x64":
            if "x86_64" in output or "x64" in output:
                return True, output.strip()
            return False, f"arquitetura nao e {expected_arch}: {output.strip()}"
        return True, output.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return False, str(e)


def validate_playwright_browsers_json(runtime_dir: Path, expected_browsers: dict) -> list[str]:
    """Validate installed browsers against browsers.json from playwright-core."""
    browsers_json = runtime_dir / "driver" / "package" / "browsers.json"
    if not browsers_json.exists():
        return ["browsers.json nao encontrado"]

    try:
        data = json.loads(browsers_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return [f"browsers.json invalido: {e}"]

    errors = []
    browsers_list = data.get("browsers", [])

    browser_map = {b["name"]: b for b in browsers_list}

    for browser_name, expected in expected_browsers.items():
        entry = browser_map.get(browser_name)
        if entry is None:
            errors.append(f"Browser {browser_name} nao encontrado em browsers.json")
            continue
        revision = entry.get("revision")
        expected_revision = expected.get("revision")
        if revision is not None and expected_revision is not None and int(revision) != int(expected_revision):
            errors.append(f"Browser {browser_name}: revisao esperada {expected_revision}, obtida {revision}")

    return errors


def is_within_root(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        return str(resolved).startswith(str(root_resolved) + os.sep) or resolved == root_resolved
    except (OSError, RuntimeError):
        return False
