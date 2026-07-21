"""Tests for playwright_runtime.manifest module."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright_runtime.manifest import InstallationManifest, MANIFEST_SCHEMA_VERSION


class TestInstallationManifest:
    def test_write_and_read(self, tmp_path):
        manifest = InstallationManifest(tmp_path)
        result = manifest.write(
            runtime_id="pw-1.60.0-chromium-1223",
            target="darwin-arm64",
            status="ready",
            components={"node": {"version": "24.18.0"}},
        )

        assert result["runtimeId"] == "pw-1.60.0-chromium-1223"
        assert result["platform"] == "darwin-arm64"
        assert result["status"] == "ready"
        assert result["components"]["node"]["version"] == "24.18.0"
        assert result["schemaVersion"] == MANIFEST_SCHEMA_VERSION

        read_data = manifest.read()
        assert read_data == result

    def test_exists(self, tmp_path):
        manifest = InstallationManifest(tmp_path)
        assert manifest.exists() is False
        manifest.write(runtime_id="x", target="x", status="ready", components={})
        assert manifest.exists() is True

    def test_read_nonexistent(self, tmp_path):
        manifest = InstallationManifest(tmp_path)
        assert manifest.read() is None

    def test_read_corrupted(self, tmp_path):
        (tmp_path / "installation-manifest.json").write_text("not json")
        manifest = InstallationManifest(tmp_path)
        assert manifest.read() is None

    def test_update_status(self, tmp_path):
        manifest = InstallationManifest(tmp_path)
        manifest.write(runtime_id="x", target="x", status="installing", components={})

        updated = manifest.update_status("ready")
        assert updated["status"] == "ready"
        assert updated["validatedAt"] is not None

    def test_get_runtime_id(self, tmp_path):
        manifest = InstallationManifest(tmp_path)
        assert manifest.get_runtime_id() is None
        manifest.write(runtime_id="pw-1", target="x", status="ready", components={})
        assert manifest.get_runtime_id() == "pw-1"

    def test_get_status(self, tmp_path):
        manifest = InstallationManifest(tmp_path)
        assert manifest.get_status() is None
        manifest.write(runtime_id="x", target="x", status="ready", components={})
        assert manifest.get_status() == "ready"

    def test_validate_schema(self, tmp_path):
        manifest = InstallationManifest(tmp_path)
        assert manifest.validate_schema() is False
        manifest.write(runtime_id="x", target="x", status="ready", components={})
        assert manifest.validate_schema() is True

    def test_validate_schema_wrong_version(self, tmp_path):
        (tmp_path / "installation-manifest.json").write_text(json.dumps({"schemaVersion": 999}))
        manifest = InstallationManifest(tmp_path)
        assert manifest.validate_schema() is False

    def test_matches_target(self, tmp_path):
        manifest = InstallationManifest(tmp_path)
        assert manifest.matches_target("darwin-arm64") is False
        manifest.write(runtime_id="x", target="darwin-arm64", status="ready", components={})
        assert manifest.matches_target("darwin-arm64") is True
        assert manifest.matches_target("darwin-x64") is False

    def test_matches_runtime_id(self, tmp_path):
        manifest = InstallationManifest(tmp_path)
        assert manifest.matches_runtime_id("pw-1") is False
        manifest.write(runtime_id="pw-1", target="x", status="ready", components={})
        assert manifest.matches_runtime_id("pw-1") is True
        assert manifest.matches_runtime_id("pw-2") is False

    def test_atomic_write(self, tmp_path):
        """Ensure write creates a tmp file first, then renames atomically."""
        manifest = InstallationManifest(tmp_path)
        manifest.write(runtime_id="x", target="x", status="ready", components={})

        manifest_file = tmp_path / "installation-manifest.json"
        assert manifest_file.exists()

        tmp_files = list(tmp_path.glob("*.json.tmp"))
        assert len(tmp_files) == 0  # tmp file should be gone after rename

    def test_manifest_file_path(self, tmp_path):
        manifest = InstallationManifest(tmp_path)
        assert manifest.manifest_file == tmp_path / "installation-manifest.json"
