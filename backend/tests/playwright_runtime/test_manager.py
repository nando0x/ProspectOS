"""Tests for playwright_runtime.manager module — the PlaywrightRuntimeManager.

These tests use mock HTTP clients, synthetic subprocess runners, and temp directories
to avoid touching real network, Node, or browsers.
"""

import json
import os
import sys
import time
import unittest.mock
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright_runtime.manager import PlaywrightRuntimeManager
from playwright_runtime.errors import (
    UnsupportedTargetError,
    PlaywrightRuntimeError,
    CancelledError,
)
from playwright_runtime.models import RuntimeState


def _make_spec(tmp_path, target="darwin-arm64", runtime_id="pw-1.60.0-chromium-1223"):
    """Create spec with darwin-arm64 as the only target (use _make_spec_for_target for other targets)."""
    spec = {
        "schemaVersion": 1,
        "runtimes": {
            "darwin-arm64": {
                "runtimeId": runtime_id,
                "playwright": {
                    "driverVersion": "1.60.0",
                    "coreVersion": "1.60.0",
                    "goModule": "playwright-community/playwright-go",
                    "goModuleVersion": "v0.6000.0",
                },
                "node": {
                    "version": "24.18.0",
                    "archive": "node-v24.18.0-darwin-arm64.tar.gz",
                    "url": "https://nodejs.org/dist/v24.18.0/node-v24.18.0-darwin-arm64.tar.gz",
                    "sha256": "e1a97e14c99c803e96c7339403282ea05a499c32f8d83defe9ef5ec66f979ed1",
                },
                "playwrightCore": {
                    "archive": "playwright-core-1.60.0.tgz",
                    "url": "https://registry.npmjs.org/playwright-core/-/playwright-core-1.60.0.tgz",
                    "sha256": "8b1df81ba75e90a41eb5c996350ea7ecc1c915ea643ec55138f91c949c5a25bf",
                },
                "browsers": {
                    "chromium": {"revision": 1223, "expectedVersion": "148.0.7778.96"},
                    "headlessShell": {"revision": 1223},
                    "ffmpeg": {"revision": 1011},
                },
                "licenses": {
                    "playwrightCore": "Apache-2.0",
                    "node": "MIT",
                    "chromium": "BSD-3-Clause",
                    "ffmpeg": "LGPL-2.1-or-later",
                },
            }
        },
    }
    spec_path = tmp_path / "playwright-runtime-targets.json"
    spec_path.write_text(json.dumps(spec))
    return spec_path, spec


class FakeDownloader:
    def __init__(self):
        self.downloads = []

    def download(self, url, expected_sha256, archive_name="", progress=None, cancel=None,
                 max_retries=3, connect_timeout=15, read_timeout=60):
        """Fake download accepting all positional args from the real Downloader."""
        self.downloads.append((url, expected_sha256, archive_name))
        from playwright_runtime.downloader import DownloadResult
        return DownloadResult(
            path=Path(f"/tmp/{archive_name}"),
            sha256=expected_sha256,
            size=1000,
            cached=False,
        )


class FakeSubprocessRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, cwd=None, env=None, timeout=30):
        self.calls.append({"cmd": cmd, "cwd": cwd, "env": env, "timeout": timeout})
        cmd_str = " ".join(str(c) for c in cmd)

        if "--version" in cmd_str and "node" in cmd_str:
            return 0, "v24.18.0", ""

        if "--version" in cmd_str and "cli.js" in cmd_str:
            return 0, "1.60.0", ""

        if "install" in cmd_str:
            return 0, "Browser installed", ""

        return 0, "", ""


@pytest.fixture
def manager_and_paths(tmp_path):
    spec_path, spec = _make_spec(tmp_path)
    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    fake_downloader = FakeDownloader()
    fake_runner = FakeSubprocessRunner()

    manager = PlaywrightRuntimeManager(
        cache_root=cache_root,
        target="darwin-arm64",
        spec_path=spec_path,
        http_client=fake_downloader,
        subprocess_runner=fake_runner,
    )

    return manager, tmp_path, spec_path, fake_downloader, fake_runner


# ── Initialization ─────────────────────────────────────────────────────


class TestInit:
    def test_init_with_valid_target(self, tmp_path):
        spec_path, spec = _make_spec(tmp_path)
        manager = PlaywrightRuntimeManager(
            cache_root=tmp_path, target="darwin-arm64", spec_path=spec_path,
            http_client=FakeDownloader(), subprocess_runner=FakeSubprocessRunner(),
        )
        assert manager._target == "darwin-arm64"
        assert manager._runtime_id == "pw-1.60.0-chromium-1223"

    def test_init_unsupported_target(self, tmp_path):
        spec_path, spec = _make_spec(tmp_path)
        with pytest.raises(UnsupportedTargetError):
            PlaywrightRuntimeManager(
                cache_root=tmp_path, target="win32-arm64", spec_path=spec_path,
                http_client=FakeDownloader(), subprocess_runner=FakeSubprocessRunner(),
            )

    def test_init_invalid_spec(self, tmp_path):
        spec_path = tmp_path / "bad.json"
        spec_path.write_text("not json")
        with pytest.raises(Exception):
            PlaywrightRuntimeManager(
                cache_root=tmp_path, target="darwin-arm64", spec_path=spec_path,
                http_client=FakeDownloader(), subprocess_runner=FakeSubprocessRunner(),
            )


# ── Inspect ────────────────────────────────────────────────────────────


class TestInspect:
    def test_not_installed(self, manager_and_paths):
        manager, *_ = manager_and_paths
        insp = manager.inspect()
        assert insp.state == RuntimeState.NOT_INSTALLED
        assert insp.runtime_id == "pw-1.60.0-chromium-1223"
        assert insp.target == "darwin-arm64"


# ── Is Ready ───────────────────────────────────────────────────────────


class TestIsReady:
    def test_not_installed(self, manager_and_paths):
        manager, *_ = manager_and_paths
        assert manager.is_ready() is False

    def test_no_manifest(self, manager_and_paths):
        manager, *_ = manager_and_paths
        manager._installation_dir.mkdir(parents=True)
        assert manager.is_ready() is False

    def test_missing_node(self, manager_and_paths):
        manager, *_ = manager_and_paths
        inst_dir = manager._installation_dir
        inst_dir.mkdir(parents=True)
        from playwright_runtime.manifest import InstallationManifest
        man = InstallationManifest(inst_dir)
        man.write(runtime_id=manager._runtime_id, target=manager._target, status="ready", components={})
        assert manager.is_ready() is False


# ── Get Environment ───────────────────────────────────────────────────


class TestGetEnvironment:
    def test_returns_dict(self, manager_and_paths):
        manager, *_ = manager_and_paths
        env = manager.get_environment()
        assert "PLAYWRIGHT_DRIVER_PATH" in env
        assert "PLAYWRIGHT_BROWSERS_PATH" in env

    def test_does_not_modify_global_env(self, manager_and_paths):
        manager, *_ = manager_and_paths
        original = os.environ.copy()
        manager.get_environment()
        assert os.environ == original


# ── Remove ─────────────────────────────────────────────────────────────


class TestRemove:
    def test_remove_installation(self, manager_and_paths):
        manager, tmp_path, *_ = manager_and_paths
        target_root = manager._installations_dir / manager._target
        target_root.mkdir(parents=True)
        (target_root / "some-install").mkdir()

        manager.remove()
        assert not target_root.exists()

    def test_remove_nonexistent(self, manager_and_paths):
        manager, *_ = manager_and_paths
        manager.remove()

    def test_view_removed_outside_removes_properly(self, manager_and_paths):
        """Remove only removes the target installation, not the whole root."""
        manager, *_ = manager_and_paths
        target_root = manager._installations_dir / manager._target
        target_root.mkdir(parents=True)
        assert target_root.exists()
        manager.remove()
        assert not target_root.exists()
        assert manager._runtime_root.exists()  # root should still exist

    def test_remove_root_raises(self, manager_and_paths):
        manager, *_ = manager_and_paths
        with pytest.raises(PlaywrightRuntimeError):
            manager._installations_dir = manager._runtime_root.parent
            manager._target = manager._runtime_root.name
            manager.remove()


# ── Validate ───────────────────────────────────────────────────────────


class TestValidate:
    def test_no_installation(self, manager_and_paths):
        manager, *_ = manager_and_paths
        val = manager.validate()
        assert val.valid is False

    def test_incomplete_installation(self, manager_and_paths):
        manager, *_ = manager_and_paths
        manager._installation_dir.mkdir(parents=True)
        val = manager.validate()
        assert val.valid is False

    def test_with_full_installation(self, manager_and_paths):
        manager, tmp_path, *_ = manager_and_paths
        self._build_valid_installation(manager)
        val = manager.validate(quick=True)
        assert val.valid, f"Validation errors: {val.errors}"

    def _build_valid_installation(self, manager):
        inst_dir = manager._installation_dir
        inst_dir.mkdir(parents=True)

        driver_dir = inst_dir / "driver"
        driver_dir.mkdir()

        node_path = driver_dir / "node"
        node_path.write_text("#!/bin/sh\necho v24.18.0")
        node_path.chmod(0o755)

        pkg_dir = driver_dir / "package"
        pkg_dir.mkdir()
        cli_path = pkg_dir / "cli.js"
        cli_path.write_text("#!/bin/sh\necho 1.60.0")
        cli_path.chmod(0o755)

        browsers_dir = inst_dir / "browsers"
        browsers_dir.mkdir()
        (browsers_dir / "chromium-1223").mkdir()
        (browsers_dir / "chromium_headless_shell-1223").mkdir()
        (browsers_dir / "ffmpeg-1011").mkdir()

        browsers_json = pkg_dir / "browsers.json"
        browsers_json.write_text(json.dumps({
            "browsers": [
                {"name": "chromium", "revision": 1223},
                {"name": "chromium-headless-shell", "revision": 1223},
                {"name": "ffmpeg", "revision": 1011},
            ]
        }))

        from playwright_runtime.manifest import InstallationManifest
        man = InstallationManifest(inst_dir)
        man.write(
            runtime_id=manager._runtime_id,
            target=manager._target,
            status="ready",
            components={
                "node": {"version": "24.18.0", "sha256": "", "path": "driver/node"},
                "playwrightCore": {"version": "1.60.0", "sha256": "", "path": "driver/package"},
                "chromium": {"revision": 1223, "path": "browsers/chromium-1223"},
                "headlessShell": {"revision": 1223, "path": "browsers/chromium_headless_shell-1223"},
                "ffmpeg": {"revision": 1011, "path": "browsers/ffmpeg-1011"},
            },
        )


# ── Diagnostics ───────────────────────────────────────────────────────


class TestDiagnostics:
    def test_basic_diagnostics(self, manager_and_paths):
        manager, *_ = manager_and_paths
        diag = manager.get_diagnostics()
        assert diag.target == "darwin-arm64"
        assert diag.runtime_id == "pw-1.60.0-chromium-1223"
        assert diag.locked is False

    def test_diagnostics_with_installation(self, manager_and_paths):
        manager, *_ = manager_and_paths
        manager._installation_dir.mkdir(parents=True)
        diag = manager.get_diagnostics()
        assert diag.state is not None


# ── Security ──────────────────────────────────────────────────────────


class TestSecurity:
    def test_get_environment_does_not_expose_secrets(self, manager_and_paths):
        manager, *_ = manager_and_paths
        env = manager.get_environment()
        assert set(env.keys()) == {"PLAYWRIGHT_DRIVER_PATH", "PLAYWRIGHT_BROWSERS_PATH"}

    def test_unsupported_target_clear_error(self, tmp_path):
        spec_path, spec = _make_spec(tmp_path)
        with pytest.raises(UnsupportedTargetError) as exc:
            PlaywrightRuntimeManager(
                cache_root=tmp_path, target="win32-arm64", spec_path=spec_path,
                http_client=FakeDownloader(), subprocess_runner=FakeSubprocessRunner(),
            )
        assert "win32-arm64" in str(exc.value)

    def test_remove_rejects_home_path(self, manager_and_paths):
        manager, *_ = manager_and_paths
        with pytest.raises(PlaywrightRuntimeError):
            manager._installations_dir = Path("/")
            manager._target = "test"
            manager.remove()


# ── Cancellation ──────────────────────────────────────────────────────


class TestCancellation:
    def test_cancel_before_install(self, manager_and_paths):
        manager, *_ = manager_and_paths
        def cancel():
            return True
        with pytest.raises(CancelledError):
            manager.install(cancel=cancel)


# ── Ensure Ready ──────────────────────────────────────────────────────


class TestEnsureReady:
    def test_ready_state_returns_immediately(self, manager_and_paths):
        manager, *_ = manager_and_paths
        with unittest.mock.patch.object(manager, '_determine_state', return_value=RuntimeState.READY):
            result = manager.ensure_ready()
            assert result.success is True
            assert result.state == RuntimeState.READY

    def test_not_installed_triggers_install(self, manager_and_paths):
        manager, *_ = manager_and_paths
        with unittest.mock.patch.object(manager, 'is_ready', return_value=False):
            with unittest.mock.patch.object(manager, '_determine_state', return_value=RuntimeState.NOT_INSTALLED):
                with unittest.mock.patch.object(manager, '_install') as mock_install:
                    mock_install.return_value = type('MockResult', (), {
                        'success': True, 'runtime_id': 'test', 'target': 'test',
                        'path': '/tmp', 'state': RuntimeState.READY, 'duration_seconds': 0,
                    })
                    result = manager.ensure_ready()
                    assert result.success is True

    def test_unsupported_detected(self, tmp_path):
        spec_path, spec = _make_spec(tmp_path)
        with pytest.raises(UnsupportedTargetError):
            manager = PlaywrightRuntimeManager(
                cache_root=tmp_path, target="linux-x64", spec_path=spec_path,
                http_client=FakeDownloader(), subprocess_runner=FakeSubprocessRunner(),
            )


# ── Runtime State Determination ───────────────────────────────────────


class TestStateDetermination:
    def test_not_installed(self, manager_and_paths):
        manager, *_ = manager_and_paths
        assert manager._determine_state() == RuntimeState.NOT_INSTALLED

    def test_unsupported(self, tmp_path):
        spec_path, spec = _make_spec(tmp_path)
        with pytest.raises(UnsupportedTargetError):
            PlaywrightRuntimeManager(
                cache_root=tmp_path, target="linux-x64", spec_path=spec_path,
                http_client=FakeDownloader(), subprocess_runner=FakeSubprocessRunner(),
            )

    def test_incomplete_no_manifest(self, manager_and_paths):
        manager, *_ = manager_and_paths
        manager._installation_dir.mkdir(parents=True)
        assert manager._determine_state() == RuntimeState.INCOMPLETE

    def test_corrupted_empty_manifest(self, manager_and_paths):
        manager, *_ = manager_and_paths
        manager._installation_dir.mkdir(parents=True)
        (manager._installation_dir / "installation-manifest.json").write_text("not json")
        assert manager._determine_state() == RuntimeState.CORRUPTED

    def test_locked_state(self, manager_and_paths):
        manager, *_ = manager_and_paths
        manager._lock.acquire()
        assert manager._determine_state() == RuntimeState.DOWNLOADING
        manager._lock.release()


# ── Resource Location ─────────────────────────────────────────────────


class TestResourceLocation:
    def test_runtime_root_created(self, manager_and_paths):
        manager, *_ = manager_and_paths
        assert manager._runtime_root.exists()

    def test_cache_directories(self, manager_and_paths):
        manager, *_ = manager_and_paths
        assert manager._downloads_dir.parent.exists()
        assert manager._staging_dir.parent.exists()


# ── Repair ─────────────────────────────────────────────────────────────


class TestRepair:
    def test_repair_without_existing(self, manager_and_paths):
        manager, *_ = manager_and_paths
        with unittest.mock.patch.object(manager, '_install') as mock_install:
            mock_install.return_value = type('MockResult', (), {
                'success': True, 'runtime_id': 'pw-1', 'target': 'test',
                'path': '/tmp', 'state': RuntimeState.READY, 'duration_seconds': 0,
            })
            result = manager.repair()
            assert result.success is True


# ── Windows Compatibility ────────────────────────────────────────────


class TestWindowsCompat:
    def test_manager_imports_on_any_platform(self):
        import playwright_runtime.manager
        assert playwright_runtime.manager is not None

    def test_lock_works_windows_style(self, tmp_path):
        from playwright_runtime.lock import InstallationLock
        lock = InstallationLock(tmp_path, "test-target", "test-id")
        assert lock.acquire() is True
        lock.release()


# ── Progress Callback ─────────────────────────────────────────────────


class TestProgress:
    def test_progress_during_install(self, manager_and_paths):
        manager, *_ = manager_and_paths
        events = []

        def progress(**kw):
            events.append(kw)

        with unittest.mock.patch.object(manager, '_install') as mock_install:
            mock_install.return_value = type('MockResult', (), {
                'success': True, 'runtime_id': 'pw-1', 'target': 'test',
                'path': '/tmp', 'state': RuntimeState.READY, 'duration_seconds': 0,
            })
            result = manager.install(progress=progress)
            assert result.success is True


# ── Second Execution ──────────────────────────────────────────────────


class TestSecondExecution:
    def test_second_install_raises(self, manager_and_paths):
        manager, *_ = manager_and_paths
        with unittest.mock.patch.object(manager, 'is_ready', return_value=True):
            with pytest.raises(PlaywrightRuntimeError):
                manager.install()

    def test_second_inspect(self, manager_and_paths):
        manager, *_ = manager_and_paths
        insp = manager.inspect()
        assert insp is not None


# ── Concurrency test ──────────────────────────────────────────────────


def test_lock_concurrency(tmp_path):
    from playwright_runtime.lock import InstallationLock
    lock1 = InstallationLock(tmp_path, "test", "id1")
    lock2 = InstallationLock(tmp_path, "test", "id2")

    assert lock1.acquire() is True
    assert lock2.acquire() is False
    lock1.release()
    assert lock2.acquire() is True
    lock2.release()


# ── Installation path safety ──────────────────────────────────────────


class TestPathSafety:
    def test_installation_path_within_cache(self, manager_and_paths):
        manager, *_ = manager_and_paths
        inst_path = manager._installation_dir
        assert str(inst_path).startswith(str(manager._runtime_root))

    def test_downloads_path_within_cache(self, manager_and_paths):
        manager, *_ = manager_and_paths
        assert str(manager._downloads_dir).startswith(str(manager._runtime_root))
