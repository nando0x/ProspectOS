"""Internal diagnostic tool — runs inside PyInstaller bundle context.

Triggered via PROSPECTOS_DIAG=1 env var on the bundled executable.
Prints JSON results to stdout and exits.
"""

import json
import os
import sys
import tempfile


def _result(name: str, status: str, detail: str = "") -> dict:
    return {"test": name, "status": status, "detail": detail}


def test_keychain() -> dict:
    try:
        import keyring
        from keyring.backends.macOS import Keyring
        keyring.set_keyring(Keyring())
    except Exception as e:
        return _result("keychain", "FAIL", f"import/setup: {e}")

    service = "ProspectOS-PR7-Local-Smoke"
    key = "diag-key"
    value = "diag-value-2026"

    try:
        keyring.set_password(service, key, value)
        retrieved = keyring.get_password(service, key)
        if retrieved != value:
            return _result("keychain", "FAIL", f"value mismatch: got {retrieved}")
        keyring.delete_password(service, key)
        deleted = keyring.get_password(service, key)
        if deleted is not None:
            return _result("keychain", "FAIL", "delete did not remove")
        return _result("keychain", "PASS")
    except Exception as e:
        return _result("keychain", "FAIL", str(e))
    finally:
        try:
            import keyring
            keyring.delete_password(service, key)
        except Exception:
            pass


def test_pdf() -> dict:
    try:
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(text="ProspectOS PR7 Smoke Test")
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.close()
        pdf.output(tmp.name)
        with open(tmp.name, "rb") as f:
            header = f.read(4)
        os.unlink(tmp.name)
        if header != b"%PDF":
            return _result("pdf", "FAIL", "no PDF header")
        return _result("pdf", "PASS")
    except Exception as e:
        return _result("pdf", "FAIL", str(e))


def test_instagram_imports() -> dict:
    try:
        import instagrapi  # noqa: F401
        from instagrapi.exceptions import (  # noqa: F401
            LoginRequired, ChallengeRequired, FeedbackRequired,
            ClientError,
        )
        return _result("instagram_imports", "PASS")
    except Exception as e:
        return _result("instagram_imports", "FAIL", str(e))


def test_env() -> dict:
    info = {
        "frozen": getattr(sys, "frozen", False),
        "meipass": getattr(sys, "_MEIPASS", None),
        "executable": sys.executable,
        "platform": sys.platform,
    }
    return _result("env", "PASS" if info["frozen"] else "INFO", json.dumps(info))


ALL_TESTS = [test_keychain, test_pdf, test_instagram_imports, test_env]


def run_all() -> list[dict]:
    return [t() for t in ALL_TESTS]


if __name__ == "__main__":
    results = run_all()
    print(json.dumps(results, indent=2, ensure_ascii=False))
    failures = [r for r in results if r["status"] == "FAIL"]
    sys.exit(1 if failures else 0)
