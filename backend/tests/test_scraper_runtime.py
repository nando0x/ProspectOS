"""Tests for scraper_runtime.py — runtime resolution, environment assembly, error mapping."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper_runtime import (
    user_message_for_runtime_error,
    RUNTIME_ERROR_MESSAGES,
    RUNTIME_PROGRESS_MESSAGES,
    resolve_and_prepare_runtime,
    ScraperRuntimeError,
)
from pathlib import Path

from playwright_runtime.errors import (
    UnsupportedTargetError,
    LockedError,
    DiskSpaceInsufficientError,
    CancelledError,
    DownloadFailedError,
    ChecksumMismatchError,
    PlaywrightRuntimeError,
)


class TestUserMessageForRuntimeError:
    def test_disk_space(self, tmp_path):
        exc = DiskSpaceInsufficientError(available=100, required=1000, path_obj=tmp_path)
        msg = user_message_for_runtime_error(exc)
        assert msg == RUNTIME_ERROR_MESSAGES["DISK_SPACE_INSUFFICIENT"]

    def test_download_failed(self):
        exc = DownloadFailedError(url="http://x", status=500)
        msg = user_message_for_runtime_error(exc)
        assert msg == RUNTIME_ERROR_MESSAGES["DOWNLOAD_FAILED"]

    def test_checksum_mismatch(self):
        exc = ChecksumMismatchError(component="node", expected="abc", actual="def")
        msg = user_message_for_runtime_error(exc)
        assert msg == RUNTIME_ERROR_MESSAGES["CHECKSUM_MISMATCH"]

    def test_unsupported_target(self):
        exc = UnsupportedTargetError("win32-x64")
        msg = user_message_for_runtime_error(exc)
        assert msg == RUNTIME_ERROR_MESSAGES["UNSUPPORTED_TARGET"]

    def test_locked(self):
        exc = LockedError(target="darwin-arm64")
        msg = user_message_for_runtime_error(exc)
        assert msg == RUNTIME_ERROR_MESSAGES["LOCKED"]

    def test_cancelled(self):
        exc = CancelledError(stage="install")
        msg = user_message_for_runtime_error(exc)
        assert msg == RUNTIME_ERROR_MESSAGES["CANCELLED"]

    def test_generic_playwright_error(self):
        exc = PlaywrightRuntimeError(code="UNKNOWN", message="something broke")
        msg = user_message_for_runtime_error(exc)
        assert msg == "Erro ao preparar ambiente de busca."

    def test_corrupted_playwright_error(self):
        exc = PlaywrightRuntimeError(
            code="PLAYWRIGHT_RUNTIME_CORRUPTED", message="files missing"
        )
        msg = user_message_for_runtime_error(exc)
        assert msg == RUNTIME_ERROR_MESSAGES["CORRUPTED_REPAIR_FAILED"]

    def test_scraper_runtime_error_passes_through(self):
        exc = ScraperRuntimeError("ambiente falhou", code="X")
        msg = user_message_for_runtime_error(exc)
        # falls through to generic — the ScraperRuntimeError is already user-friendly
        assert msg


class TestRuntimeProgressMessages:
    def test_all_stages_have_messages(self):
        expected_stages = [
            "checking", "downloading_playwright_core", "downloading_node",
            "verifying_downloads", "extracting_playwright_core", "extracting_node",
            "assembling_driver", "validating_driver", "installing_browser",
            "validating_browser", "publishing", "ready",
        ]
        for stage in expected_stages:
            assert stage in RUNTIME_PROGRESS_MESSAGES, f"missing message for {stage}"
            assert RUNTIME_PROGRESS_MESSAGES[stage]

    def test_no_technical_details(self):
        disallowed = ["sha256", "url", "node", "chromium", "/tmp", "hash"]
        for msg in RUNTIME_PROGRESS_MESSAGES.values():
            for token in disallowed:
                assert token not in msg.lower(), f"technical token '{token}' in '{msg}'"


class TestResolveAndPrepareRuntime:
    def test_returns_tuple(self, monkeypatch, tmp_path):
        scraper = tmp_path / "google-maps-scraper"
        scraper.write_text("fake")
        scraper.chmod(0o755)

        monkeypatch.setattr("runtime_targets.current_target", lambda: "darwin-arm64")
        monkeypatch.setattr("runtime_targets.resolve_scraper", lambda: scraper)
        monkeypatch.setattr("runtime_targets.validate_executable", lambda p, l: None)

        class FakeManager:
            def ensure_ready(self, progress=None, cancel=None):
                return type("Installation", (), {"target": "darwin-arm64", "runtime_id": "x", "path": str(tmp_path)})()
            def get_environment(self):
                return {"PLAYWRIGHT_DRIVER_PATH": str(tmp_path / "driver"), "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "browsers")}

        monkeypatch.setattr("scraper_runtime.PlaywrightRuntimeManager", lambda: FakeManager())
        (tmp_path / "driver").mkdir()
        (tmp_path / "browsers").mkdir()

        path, env = resolve_and_prepare_runtime()
        assert isinstance(path, Path)
        assert "PLAYWRIGHT_DRIVER_PATH" in env
        assert "PLAYWRIGHT_BROWSERS_PATH" in env

    def test_non_darwin_returns_empty_env(self, monkeypatch, tmp_path):
        scraper = tmp_path / "google-maps-scraper"
        scraper.write_text("fake")
        scraper.chmod(0o755)

        monkeypatch.setattr("runtime_targets.current_target", lambda: "win32-x64")
        monkeypatch.setattr("runtime_targets.resolve_scraper", lambda: scraper)
        monkeypatch.setattr("runtime_targets.validate_executable", lambda p, l: None)

        path, env = resolve_and_prepare_runtime()
        assert env == {}

    def test_scraper_not_found_raises(self, monkeypatch):
        monkeypatch.setattr("runtime_targets.current_target", lambda: "darwin-arm64")
        monkeypatch.setattr("runtime_targets.resolve_scraper", lambda: Path("/nonexistent"))
        monkeypatch.setattr("runtime_targets.validate_executable", lambda p, l: (_ for _ in ()).throw(FileNotFoundError("not found")))

        with pytest.raises(FileNotFoundError):
            resolve_and_prepare_runtime()
