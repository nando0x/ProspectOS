"""Tests for playwright_runtime.lock module."""

import os
import sys
import time
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright_runtime.lock import InstallationLock, check_locked
from playwright_runtime.errors import LockedError


class TestInstallationLock:
    def test_acquire_and_release(self, tmp_path):
        lock = InstallationLock(tmp_path, "darwin-arm64", "pw-1.60.0-chromium-1223")
        assert lock.acquire() is True
        assert lock._held is True
        lock.release()
        assert lock._held is False

    def test_double_acquire_fails(self, tmp_path):
        lock1 = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        lock2 = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        assert lock1.acquire() is True
        assert lock2.acquire() is False
        lock1.release()

    def test_lock_file_created(self, tmp_path):
        lock = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        lock.acquire()
        assert (tmp_path / "darwin-arm64.lock").exists()
        lock.release()
        assert not (tmp_path / "darwin-arm64.lock").exists()

    def test_lock_file_content(self, tmp_path):
        lock = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        lock.acquire()
        data = json.loads((tmp_path / "darwin-arm64.lock").read_text())
        assert data["pid"] == os.getpid()
        assert data["target"] == "darwin-arm64"
        assert data["runtimeId"] == "pw-1"
        lock.release()

    def test_is_locked_true(self, tmp_path):
        lock = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        lock.acquire()
        assert lock.is_locked() is True
        lock.release()

    def test_is_locked_false_after_release(self, tmp_path):
        lock = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        lock.acquire()
        lock.release()
        assert lock.is_locked() is False

    def test_is_locked_false_without_acquire(self, tmp_path):
        lock = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        assert lock.is_locked() is False

    def test_context_manager_acquires_and_releases(self, tmp_path):
        lock = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        with lock:
            assert lock._held is True
            assert lock.lock_file.exists()
        assert lock._held is False
        assert not lock.lock_file.exists()

    def test_context_manager_raises_locked(self, tmp_path):
        lock1 = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        lock2 = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        lock1.acquire()
        with pytest.raises(LockedError):
            with lock2:
                pass
        lock1.release()

    def test_stale_lock_different_pid(self, tmp_path):
        """Simulate stale lock from dead process."""
        lock_file = tmp_path / "darwin-arm64.lock"
        stale_data = {"pid": 999999, "timestamp": time.time(), "target": "darwin-arm64", "runtimeId": "pw-1"}
        lock_file.write_text(json.dumps(stale_data))

        lock = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        assert lock.is_locked() is False
        assert lock.acquire() is True
        lock.release()

    def test_stale_lock_old_timestamp(self, tmp_path):
        """Simulate stale lock with very old timestamp."""
        lock_file = tmp_path / "darwin-arm64.lock"
        stale_data = {"pid": os.getpid(), "timestamp": time.time() - 7200, "target": "darwin-arm64", "runtimeId": "pw-1"}
        lock_file.write_text(json.dumps(stale_data))

        lock = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        assert lock.is_locked() is False
        assert lock.acquire() is True
        lock.release()

    def test_invalid_lock_file(self, tmp_path):
        """Corrupted lock file should be treated as stale."""
        lock_file = tmp_path / "darwin-arm64.lock"
        lock_file.write_text("not-json")

        lock = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        assert lock.is_locked() is False
        assert lock.acquire() is True
        lock.release()

    def test_check_locked(self, tmp_path):
        lock = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        assert check_locked(tmp_path, "darwin-arm64") is False
        lock.acquire()
        assert check_locked(tmp_path, "darwin-arm64") is True
        lock.release()
        assert check_locked(tmp_path, "darwin-arm64") is False

    def test_release_twice_no_error(self, tmp_path):
        lock = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        lock.acquire()
        lock.release()
        lock.release()  # should not raise

    def test_acquire_after_stale_release(self, tmp_path):
        lock = InstallationLock(tmp_path, "darwin-arm64", "pw-1")
        lock.acquire()
        lock.release()
        assert lock.acquire() is True
        lock.release()
