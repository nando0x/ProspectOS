"""Data models and enums for Playwright runtime management."""

import enum
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


class RuntimeState(enum.Enum):
    NOT_INSTALLED = "not_installed"
    DOWNLOADING = "downloading"
    STAGING = "staging"
    EXTRACTING = "extracting"
    INSTALLING_BROWSERS = "installing_browsers"
    VALIDATING = "validating"
    READY = "ready"
    INCOMPLETE = "incomplete"
    CORRUPTED = "corrupted"
    REPAIRING = "repairing"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class ProgressStage(enum.Enum):
    CHECKING = "checking"
    DOWNLOADING_PLAYWRIGHT_CORE = "downloading_playwright_core"
    DOWNLOADING_NODE = "downloading_node"
    VERIFYING_DOWNLOADS = "verifying_downloads"
    EXTRACTING_PLAYWRIGHT_CORE = "extracting_playwright_core"
    EXTRACTING_NODE = "extracting_node"
    ASSEMBLING_DRIVER = "assembling_driver"
    VALIDATING_DRIVER = "validating_driver"
    INSTALLING_BROWSER = "installing_browser"
    VALIDATING_BROWSER = "validating_browser"
    PUBLISHING = "publishing"
    READY = "ready"
    REPAIRING = "repairing"


@dataclass
class ProgressEvent:
    stage: ProgressStage
    component: str = ""
    completed_bytes: int = 0
    total_bytes: int = 0
    percent: float = 0.0
    message: str = ""

    def to_dict(self):
        return {
            "stage": self.stage.value,
            "component": self.component,
            "completedBytes": self.completed_bytes,
            "totalBytes": self.total_bytes,
            "percent": self.percent,
            "message": self.message,
        }


@dataclass
class ComponentInfo:
    version: str = ""
    sha256: str = ""
    source: str = ""
    path: str = ""
    architecture: str = ""
    exists: bool = False

    def to_dict(self):
        return asdict(self)


@dataclass
class RuntimeInspection:
    state: RuntimeState
    runtime_id: str = ""
    target: str = ""
    root: str = ""
    components: dict[str, ComponentInfo] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    details: str = ""

    def to_dict(self):
        return {
            "state": self.state.value,
            "runtimeId": self.runtime_id,
            "target": self.target,
            "root": self.root,
            "components": {k: v.to_dict() for k, v in self.components.items()},
            "errors": self.errors,
            "details": self.details,
        }


@dataclass
class RuntimeInstallation:
    success: bool
    runtime_id: str
    target: str
    path: str
    state: RuntimeState
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "success": self.success,
            "runtimeId": self.runtime_id,
            "target": self.target,
            "path": self.path,
            "state": self.state.value,
            "durationSeconds": self.duration_seconds,
            "errors": self.errors,
        }


@dataclass
class RuntimeValidation:
    valid: bool
    runtime_id: str
    target: str
    quick: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    component_versions: dict[str, str] = field(default_factory=dict)

    def to_dict(self):
        return {
            "valid": self.valid,
            "runtimeId": self.runtime_id,
            "target": self.target,
            "quick": self.quick,
            "errors": self.errors,
            "warnings": self.warnings,
            "componentVersions": self.component_versions,
        }


@dataclass
class RuntimeDiagnostics:
    target: str
    runtime_id: str
    state: str
    root: str
    free_disk_bytes: int
    locked: bool
    manifest: dict[str, Any] | None
    component_versions: dict[str, str]
    component_paths: dict[str, str]
    last_validation: str
    validation_errors: list[str]

    def to_dict(self):
        return asdict(self)
