"""Cross-platform file-based locking for Playwright runtime installation.

Uses O_CREAT | O_EXCL for atomic lock acquisition.
Handles stale locks by PID and age.
"""

import os
import sys
import time
import json
import errno
import logging
import platform
from pathlib import Path

logger = logging.getLogger(__name__)

STALE_LOCK_AGE_SECONDS = 3600  # 1 hour


def _can_use_o_excl():
    """Check if the platform supports O_CREAT|O_EXCL natively."""
    return sys.platform != "win32"


class InstallationLock:
    """File-based lock for installation operations."""

    def __init__(self, lock_dir: Path, target: str, runtime_id: str):
        self.lock_dir = lock_dir
        self.target = target
        self.runtime_id = runtime_id
        self.lock_file = lock_dir / f"{target}.lock"
        self._held = False

    def acquire(self) -> bool:
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        if self._held:
            return True

        if self.lock_file.exists():
            if not self._is_stale():
                return False
            logger.warning("Removendo lock stale: %s", self.lock_file)
            self.lock_file.unlink(missing_ok=True)

        try:
            data = {
                "pid": os.getpid(),
                "timestamp": time.time(),
                "target": self.target,
                "runtimeId": self.runtime_id,
            }
            if _can_use_o_excl():
                fd = os.open(str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                with os.fdopen(fd, "w") as f:
                    json.dump(data, f)
            else:
                # Windows fallback: try to create exclusively
                if self.lock_file.exists():
                    return False
                self.lock_file.write_text(json.dumps(data), encoding="utf-8")
            self._held = True
            return True
        except (OSError, IOError) as e:
            if getattr(e, "errno", None) == errno.EEXIST:
                return False
            raise

    def release(self):
        if self._held and self.lock_file.exists():
            try:
                self.lock_file.unlink(missing_ok=True)
            except Exception:
                logger.exception("Erro ao remover lock: %s", self.lock_file)
        self._held = False

    def is_locked(self) -> bool:
        if not self.lock_file.exists():
            return False
        if self._is_stale():
            return False
        return True

    def _is_stale(self) -> bool:
        try:
            data = json.loads(self.lock_file.read_text(encoding="utf-8"))
            pid = data.get("pid")
            timestamp = data.get("timestamp", 0)

            if pid and pid != os.getpid():
                if not self._pid_exists(pid):
                    return True

            if time.time() - timestamp > STALE_LOCK_AGE_SECONDS:
                return True

            return False
        except (json.JSONDecodeError, OSError, IOError):
            return True

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        if sys.platform == "win32":
            try:
                import ctypes
                handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                    return True
                return False
            except Exception:
                return True
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def __enter__(self):
        acquired = self.acquire()
        if not acquired:
            from .errors import LockedError
            raise LockedError(target=self.target)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def check_locked(lock_dir: Path, target: str) -> bool:
    lock_file = lock_dir / f"{target}.lock"
    return lock_file.exists()
