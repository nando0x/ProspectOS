"""Tests for playwright_runtime.validator module."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright_runtime.validator import (
    validate_file_exists,
    validate_is_file,
    validate_is_executable,
    validate_sha256,
    run_subprocess,
    check_architecture,
    validate_playwright_browsers_json,
    is_within_root,
)


class TestValidateFileExists:
    def test_exists(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert validate_file_exists(f) is True

    def test_not_exists(self, tmp_path):
        assert validate_file_exists(tmp_path / "nope.txt") is False


class TestValidateIsFile:
    def test_is_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert validate_is_file(f) is True

    def test_is_directory(self, tmp_path):
        d = tmp_path / "subdir"
        d.mkdir()
        assert validate_is_file(d) is False

    def test_not_exists(self, tmp_path):
        assert validate_is_file(tmp_path / "nope") is False


class TestValidateIsExecutable:
    def test_executable(self, tmp_path):
        f = tmp_path / "script.sh"
        f.write_text("#!/bin/sh")
        f.chmod(0o755)
        assert validate_is_executable(f) is True

    def test_not_executable(self, tmp_path):
        f = tmp_path / "script.sh"
        f.write_text("content")
        f.chmod(0o644)
        if sys.platform != "win32":
            assert validate_is_executable(f) is False


class TestValidateSha256:
    def test_matches(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"test data")
        import hashlib
        expected = hashlib.sha256(b"test data").hexdigest()
        assert validate_sha256(f, expected) is True

    def test_mismatch(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"test data")
        assert validate_sha256(f, "0" * 64) is False

    def test_file_not_found(self, tmp_path):
        assert validate_sha256(tmp_path / "nope", "x") is False


class TestRunSubprocess:
    def test_success(self):
        rc, out, err = run_subprocess(["echo", "hello"])
        assert rc == 0
        assert "hello" in out

    def test_not_found(self):
        rc, out, err = run_subprocess(["/nonexistent/command"])
        assert rc != 0

    def test_timeout(self):
        rc, out, err = run_subprocess(["sleep", "10"], timeout=0.1)
        assert rc == -1
        assert "TIMEOUT" in err


class TestCheckArchitecture:
    def test_checks_file_command(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x7fELF")
        f.chmod(0o755)
        result, msg = check_architecture(f, "arm64")
        assert isinstance(result, bool)
        assert isinstance(msg, str)

    def test_nonexistent_file(self, tmp_path):
        result, msg = check_architecture(tmp_path / "nope", "arm64")
        assert result is False


class TestValidatePlaywrightBrowsersJson:
    def test_valid_browsers_json(self, tmp_path):
        runtime_dir = tmp_path / "runtime"
        driver_pkg = runtime_dir / "driver" / "package"
        driver_pkg.mkdir(parents=True)

        data = {
            "browsers": [
                {"name": "chromium", "revision": 1223},
                {"name": "chromium-headless-shell", "revision": 1223},
                {"name": "ffmpeg", "revision": 1011},
            ]
        }
        (driver_pkg / "browsers.json").write_text(json.dumps(data))

        expected = {
            "chromium": {"revision": 1223},
            "chromium-headless-shell": {"revision": 1223},
            "ffmpeg": {"revision": 1011},
        }

        errors = validate_playwright_browsers_json(runtime_dir, expected)
        assert len(errors) == 0

    def test_missing_browser_json(self, tmp_path):
        errors = validate_playwright_browsers_json(tmp_path, {})
        assert len(errors) == 1
        assert "nao encontrado" in errors[0]

    def test_wrong_revision(self, tmp_path):
        runtime_dir = tmp_path / "runtime"
        driver_pkg = runtime_dir / "driver" / "package"
        driver_pkg.mkdir(parents=True)

        data = {"browsers": [{"name": "chromium", "revision": 999}]}
        (driver_pkg / "browsers.json").write_text(json.dumps(data))

        expected = {"chromium": {"revision": 1223}}
        errors = validate_playwright_browsers_json(runtime_dir, expected)
        assert len(errors) == 1
        assert "1223" in errors[0]

    def test_invalid_json(self, tmp_path):
        runtime_dir = tmp_path / "runtime"
        driver_pkg = runtime_dir / "driver" / "package"
        driver_pkg.mkdir(parents=True)
        (driver_pkg / "browsers.json").write_text("not json")

        errors = validate_playwright_browsers_json(runtime_dir, {})
        assert len(errors) == 1


class TestIsWithinRoot:
    def test_within_root(self, tmp_path):
        child = tmp_path / "sub" / "file.txt"
        assert is_within_root(child, tmp_path) is True

    def test_outside_root(self, tmp_path):
        outside = tmp_path.parent / "outside.txt"
        assert is_within_root(outside, tmp_path) is False

    def test_equal_to_root(self, tmp_path):
        assert is_within_root(tmp_path, tmp_path) is True
