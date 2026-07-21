"""Tests for playwright_runtime.models module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright_runtime.models import (
    RuntimeState,
    ProgressStage,
    ProgressEvent,
    ComponentInfo,
    RuntimeInspection,
    RuntimeInstallation,
    RuntimeValidation,
    RuntimeDiagnostics,
)


class TestRuntimeState:
    def test_values(self):
        assert RuntimeState.NOT_INSTALLED.value == "not_installed"
        assert RuntimeState.READY.value == "ready"
        assert RuntimeState.INCOMPLETE.value == "incomplete"
        assert RuntimeState.CORRUPTED.value == "corrupted"
        assert RuntimeState.UNSUPPORTED.value == "unsupported"
        assert RuntimeState.FAILED.value == "failed"

    def test_all_unique(self):
        values = [s.value for s in RuntimeState]
        assert len(values) == len(set(values))


class TestProgressStage:
    def test_values(self):
        assert ProgressStage.DOWNLOADING_NODE.value == "downloading_node"
        assert ProgressStage.READY.value == "ready"

    def test_all_unique(self):
        values = [s.value for s in ProgressStage]
        assert len(values) == len(set(values))


class TestProgressEvent:
    def test_creation(self):
        event = ProgressEvent(
            stage=ProgressStage.DOWNLOADING_NODE,
            component="node-v24.18.0",
            completed_bytes=500,
            total_bytes=1000,
            percent=50.0,
            message="Downloading Node.js",
        )
        assert event.stage == ProgressStage.DOWNLOADING_NODE
        assert event.percent == 50.0

    def test_to_dict(self):
        event = ProgressEvent(stage=ProgressStage.READY, message="Ready")
        d = event.to_dict()
        assert d["stage"] == "ready"
        assert d["message"] == "Ready"


class TestComponentInfo:
    def test_creation(self):
        info = ComponentInfo(
            version="1.60.0",
            sha256="abc123",
            source="npm",
            path="driver/package",
            architecture="arm64",
            exists=True,
        )
        assert info.version == "1.60.0"

    def test_to_dict(self):
        info = ComponentInfo(version="1.0")
        d = info.to_dict()
        assert d["version"] == "1.0"


class TestRuntimeInspection:
    def test_creation(self):
        insp = RuntimeInspection(
            state=RuntimeState.READY,
            runtime_id="pw-1.60.0-chromium-1223",
            target="darwin-arm64",
        )
        assert insp.state == RuntimeState.READY

    def test_to_dict(self):
        insp = RuntimeInspection(state=RuntimeState.NOT_INSTALLED, details="none")
        d = insp.to_dict()
        assert d["state"] == "not_installed"
        assert d["details"] == "none"


class TestRuntimeInstallation:
    def test_creation(self):
        inst = RuntimeInstallation(
            success=True,
            runtime_id="pw-1.60.0-chromium-1223",
            target="darwin-arm64",
            path="/tmp/runtime",
            state=RuntimeState.READY,
            duration_seconds=120.5,
        )
        assert inst.success is True

    def test_to_dict(self):
        inst = RuntimeInstallation(
            success=False,
            runtime_id="x",
            target="x",
            path="/x",
            state=RuntimeState.FAILED,
            errors=["connection error"],
        )
        d = inst.to_dict()
        assert d["success"] is False
        assert d["errors"] == ["connection error"]


class TestRuntimeValidation:
    def test_creation(self):
        val = RuntimeValidation(
            valid=True,
            runtime_id="pw-1.60.0-chromium-1223",
            target="darwin-arm64",
            component_versions={"node": "v24.18.0"},
        )
        assert val.valid is True

    def test_to_dict(self):
        val = RuntimeValidation(valid=False, runtime_id="x", target="x", errors=["missing node"])
        d = val.to_dict()
        assert d["valid"] is False
        assert "missing node" in d["errors"]


class TestRuntimeDiagnostics:
    def test_creation(self):
        diag = RuntimeDiagnostics(
            target="darwin-arm64",
            runtime_id="pw-1.60.0-chromium-1223",
            state="ready",
            root="/tmp/runtime",
            free_disk_bytes=1000000,
            locked=False,
            manifest=None,
            component_versions={"node": "v24.18.0"},
            component_paths={"node": "driver/node"},
            last_validation="2026-07-20T00:00:00",
            validation_errors=[],
        )
        assert diag.target == "darwin-arm64"

    def test_to_dict(self):
        diag = RuntimeDiagnostics(
            target="x", runtime_id="x", state="x", root="/x",
            free_disk_bytes=0, locked=False, manifest=None,
            component_versions={}, component_paths={},
            last_validation="", validation_errors=[],
        )
        d = diag.to_dict()
        assert d["target"] == "x"
