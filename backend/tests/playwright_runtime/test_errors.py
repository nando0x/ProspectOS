"""Tests for playwright_runtime.errors module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright_runtime.errors import (
    PlaywrightRuntimeError,
    UnsupportedTargetError,
    SpecInvalidError,
    LockedError,
    DiskSpaceInsufficientError,
    DownloadFailedError,
    DownloadTimeoutError,
    ChecksumMismatchError,
    ArchiveInvalidError,
    ExtractionFailedError,
    PathTraversalError,
    NodeInvalidError,
    DriverInvalidError,
    BrowserInstallFailedError,
    BrowserInvalidError,
    IncompleteInstallationError,
    CorruptedInstallationError,
    ValidationFailedError,
    CancelledError,
)


class TestPlaywrightRuntimeError:
    def test_base_error(self):
        err = PlaywrightRuntimeError(code="TEST", message="test error")
        assert err.code == "TEST"
        assert str(err) == "test error"

    def test_to_dict(self):
        err = PlaywrightRuntimeError(code="TEST", message="msg", component="pw", target="darwin-arm64", suggestion="fix")
        d = err.to_dict()
        assert d["code"] == "TEST"
        assert d["component"] == "pw"
        assert d["target"] == "darwin-arm64"
        assert d["suggestion"] == "fix"

    def test_to_dict_no_optional(self):
        err = PlaywrightRuntimeError(code="TEST", message="msg")
        d = err.to_dict()
        assert d["code"] == "TEST"
        assert d["message"] == "msg"


class TestUnsupportedTargetError:
    def test_default_message(self):
        err = UnsupportedTargetError(target="win32-arm64")
        assert err.code == "PLAYWRIGHT_RUNTIME_UNSUPPORTED_TARGET"
        assert "win32-arm64" in str(err)
        assert err.target == "win32-arm64"

    def test_custom_message(self):
        err = UnsupportedTargetError(target="x", message="custom")
        assert "custom" in str(err)


class TestSpecInvalidError:
    def test_with_detail(self):
        err = SpecInvalidError(detail="missing field")
        assert "missing field" in str(err)

    def test_without_detail(self):
        err = SpecInvalidError()
        assert "invalida" in str(err)


class TestLockedError:
    def test_creation(self):
        err = LockedError(target="darwin-arm64")
        assert "darwin-arm64" in str(err)
        assert err.code == "PLAYWRIGHT_RUNTIME_LOCKED"


class TestDiskSpaceInsufficientError:
    def test_creation(self):
        err = DiskSpaceInsufficientError(available=100, required=500, path_obj=Path("/tmp"))
        assert err.code == "PLAYWRIGHT_RUNTIME_DISK_SPACE_INSUFFICIENT"
        assert err.available == 100
        assert err.required == 500


class TestDownloadFailedError:
    def test_with_status(self):
        err = DownloadFailedError(url="https://example.com/file", status_code=404)
        assert "404" in str(err)
        assert err.status_code == 404

    def test_without_status(self):
        err = DownloadFailedError(url="https://example.com/file")
        assert "falhou" in str(err)


class TestDownloadTimeoutError:
    def test_creation(self):
        err = DownloadTimeoutError(url="https://example.com/file", timeout=30)
        assert "30" in str(err)


class TestChecksumMismatchError:
    def test_creation(self):
        err = ChecksumMismatchError(
            component="node-v24.18.0",
            expected="abc123",
            actual="def456",
            path_obj=Path("/tmp/file"),
        )
        assert err.component == "node-v24.18.0"
        assert err.expected == "abc123"
        assert err.actual == "def456"


class TestArchiveInvalidError:
    def test_with_detail(self):
        err = ArchiveInvalidError(path_obj=Path("/tmp/archive.tgz"), detail="not a tar")
        assert "not a tar" in str(err)


class TestExtractionFailedError:
    def test_creation(self):
        err = ExtractionFailedError(path_obj=Path("/tmp/archive.tgz"))
        assert "Falha" in str(err)


class TestPathTraversalError:
    def test_creation(self):
        err = PathTraversalError(entry_path="../../etc/passwd")
        assert "traversal" in str(err).lower()


class TestNodeInvalidError:
    def test_with_detail(self):
        err = NodeInvalidError(detail="version mismatch")
        assert "version mismatch" in str(err)


class TestDriverInvalidError:
    def test_creation(self):
        err = DriverInvalidError(detail="cli.js missing")
        assert "cli.js" in str(err)


class TestBrowserInstallFailedError:
    def test_with_exit_code(self):
        err = BrowserInstallFailedError(browser="chromium", exit_code=1, stderr="error output")
        assert err.exit_code == 1
        assert err.stderr == "error output"

    def test_without_exit_code(self):
        err = BrowserInstallFailedError(browser="chromium")
        assert err.browser == "chromium"


class TestBrowserInvalidError:
    def test_creation(self):
        err = BrowserInvalidError(browser="chromium", detail="not found")
        assert "chromium" in str(err)


class TestIncompleteInstallationError:
    def test_with_missing(self):
        err = IncompleteInstallationError(target="darwin-arm64", missing_components=["node", "chromium"])
        assert err.missing_components == ["node", "chromium"]
        assert "node" in str(err)


class TestCorruptedInstallationError:
    def test_creation(self):
        err = CorruptedInstallationError(target="darwin-arm64", detail="manifest missing")
        assert "manifest" in str(err)


class TestValidationFailedError:
    def test_with_errors(self):
        err = ValidationFailedError(errors=["node missing", "browser missing"])
        assert len(err.validation_errors) == 2


class TestCancelledError:
    def test_with_stage(self):
        err = CancelledError(stage="download")
        assert "download" in str(err)

    def test_without_stage(self):
        err = CancelledError()
        assert "cancelada" in str(err)


class TestErrorCodes:
    def test_all_error_codes_unique(self):
        instances = [
            UnsupportedTargetError(target="x"),
            SpecInvalidError(detail="x"),
            LockedError(target="x"),
            DiskSpaceInsufficientError(available=0, required=1, path_obj=Path("/tmp")),
            DownloadFailedError(url="https://x"),
            DownloadTimeoutError(url="https://x", timeout=30),
            ChecksumMismatchError(component="x", expected="a", actual="b"),
            ArchiveInvalidError(path_obj=Path("/tmp/x")),
            ExtractionFailedError(path_obj=Path("/tmp/x")),
            PathTraversalError(entry_path="../x"),
            NodeInvalidError(detail="x"),
            DriverInvalidError(detail="x"),
            BrowserInstallFailedError(browser="x"),
            BrowserInvalidError(browser="x"),
            IncompleteInstallationError(target="x"),
            CorruptedInstallationError(target="x"),
            ValidationFailedError(),
            CancelledError(),
        ]
        codes = [e.code for e in instances]
        assert len(codes) == len(set(codes)), f"Codigos duplicados: {codes}"
