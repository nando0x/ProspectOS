"""Installation manifest — records metadata about a completed Playwright runtime installation."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_SCHEMA_VERSION = 1
MANIFEST_FILENAME = "installation-manifest.json"


class InstallationManifest:
    """Read, write, and validate installation manifests."""

    def __init__(self, manifest_dir: Path):
        self.manifest_dir = manifest_dir
        self.manifest_file = manifest_dir / MANIFEST_FILENAME

    def exists(self) -> bool:
        return self.manifest_file.exists()

    def read(self) -> dict[str, Any] | None:
        if not self.manifest_file.exists():
            return None
        try:
            data = json.loads(self.manifest_file.read_text(encoding="utf-8"))
            return data
        except (json.JSONDecodeError, OSError):
            return None

    def write(self, runtime_id: str, target: str, status: str, components: dict) -> dict[str, Any]:
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        manifest = {
            "schemaVersion": MANIFEST_SCHEMA_VERSION,
            "runtimeId": runtime_id,
            "platform": target,
            "status": status,
            "installedAt": now,
            "validatedAt": now,
            "components": components,
        }
        tmp = self.manifest_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.manifest_file)
        return manifest

    def update_status(self, status: str) -> dict[str, Any] | None:
        data = self.read()
        if data is None:
            return None
        data["status"] = status
        data["validatedAt"] = datetime.now(timezone.utc).isoformat()
        tmp = self.manifest_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.manifest_file)
        return data

    def get_runtime_id(self) -> str | None:
        data = self.read()
        if data:
            return data.get("runtimeId")
        return None

    def get_status(self) -> str | None:
        data = self.read()
        if data:
            return data.get("status")
        return None

    def validate_schema(self) -> bool:
        data = self.read()
        if data is None:
            return False
        return data.get("schemaVersion") == MANIFEST_SCHEMA_VERSION

    def matches_target(self, target: str) -> bool:
        data = self.read()
        if data is None:
            return False
        return data.get("platform") == target

    def matches_runtime_id(self, runtime_id: str) -> bool:
        data = self.read()
        if data is None:
            return False
        return data.get("runtimeId") == runtime_id
