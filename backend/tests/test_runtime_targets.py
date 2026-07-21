"""Testes de runtime_targets.py — resolução de binários nativos por plataforma."""

import json
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import runtime_targets as rt


# ---------------------------------------------------------------------------
# normalize_platform
# ---------------------------------------------------------------------------

class TestNormalizePlatform:
    def test_darwin(self):
        assert rt.normalize_platform("darwin") == "darwin"

    def test_win32(self):
        assert rt.normalize_platform("win32") == "win32"

    def test_linux(self):
        assert rt.normalize_platform("linux") == "linux"

    def test_unknown(self):
        assert rt.normalize_platform("freebsd") is None

    def test_empty(self):
        assert rt.normalize_platform("") is None

    def test_default_uses_sys_platform(self):
        assert rt.normalize_platform() in ("darwin", "win32", "linux", None)


# ---------------------------------------------------------------------------
# normalize_architecture
# ---------------------------------------------------------------------------

class TestNormalizeArchitecture:
    def test_arm64(self):
        assert rt.normalize_architecture("arm64") == "arm64"

    def test_aarch64(self):
        assert rt.normalize_architecture("aarch64") == "arm64"

    def test_x64(self):
        assert rt.normalize_architecture("x64") == "x64"

    def test_amd64(self):
        assert rt.normalize_architecture("AMD64") == "x64"

    def test_x86_64(self):
        assert rt.normalize_architecture("x86_64") == "x64"

    def test_unknown(self):
        assert rt.normalize_architecture("ia32") is None

    def test_default_uses_platform_machine(self):
        result = rt.normalize_architecture()
        assert result in ("arm64", "x64", None)


# ---------------------------------------------------------------------------
# current_target
# ---------------------------------------------------------------------------

class TestCurrentTarget:
    def test_returns_canonical_format(self):
        target = rt.current_target()
        assert "-" in target
        plat, arch = target.split("-", 1)
        assert plat in ("darwin", "win32", "linux")
        assert arch in ("arm64", "x64")

    def test_unknown_platform_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "freebsd")
        monkeypatch.setattr(rt._platform, "machine", lambda: "x86_64")
        with pytest.raises(RuntimeError, match="nao suportado"):
            rt.current_target()

    def test_unknown_arch_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(rt._platform, "machine", lambda: "ia32")
        with pytest.raises(RuntimeError, match="nao suportado"):
            rt.current_target()


# ---------------------------------------------------------------------------
# safe_join
# ---------------------------------------------------------------------------

class TestSafeJoin:
    def test_normal_relative_path(self):
        result = rt.safe_join("/tmp/root", "backend/ProspectOS")
        assert result == (Path("/tmp/root") / "backend/ProspectOS").resolve()

    def test_nested_path(self):
        result = rt.safe_join("/tmp/root", "scraper/google-maps-scraper")
        assert result == (Path("/tmp/root") / "scraper/google-maps-scraper").resolve()

    def test_with_spaces(self):
        result = rt.safe_join("/tmp/root", "my app/backend")
        assert result == (Path("/tmp/root") / "my app/backend").resolve()

    def test_absolute_path_raises(self):
        with pytest.raises(ValueError, match="absoluto"):
            rt.safe_join("/tmp/root", "/etc/passwd")

    def test_windows_absolute_path_raises(self):
        with pytest.raises(ValueError, match="absoluto"):
            rt.safe_join("/tmp/root", "C:\\absolute.exe")

    def test_traversal_raises(self):
        with pytest.raises(ValueError, match="traversal"):
            rt.safe_join("/tmp/root", "../outside")

    def test_deep_traversal_raises(self):
        with pytest.raises(ValueError, match="traversal"):
            rt.safe_join("/tmp/root", "../../etc/passwd")

    def test_normalized_traversal_raises(self):
        with pytest.raises(ValueError, match="traversal"):
            rt.safe_join("/tmp/root", "foo/../../etc/passwd")

    def test_empty_relative_path_raises(self):
        with pytest.raises(ValueError, match="vazio"):
            rt.safe_join("/tmp/root", "")

    def test_unicode_path(self):
        result = rt.safe_join("/tmp", "café/ProspectOS")
        assert result == (Path("/tmp") / "café/ProspectOS").resolve()


# ---------------------------------------------------------------------------
# load_runtime_manifest
# ---------------------------------------------------------------------------

class TestLoadRuntimeManifest:
    def test_valid_manifest(self, tmp_path):
        m = tmp_path / "manifest.json"
        m.write_text(json.dumps({
            "schemaVersion": 1,
            "targets": {
                "darwin-arm64": {
                    "backend": {"name": "ProspectOS"},
                    "scraper": {"name": "google-maps-scraper"},
                },
            },
        }))
        data = rt.load_runtime_manifest(m)
        assert data["schemaVersion"] == 1
        assert data["targets"]["darwin-arm64"]["backend"]["name"] == "ProspectOS"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="nao encontrado"):
            rt.load_runtime_manifest("/nao/existe.json")

    def test_invalid_json(self, tmp_path):
        m = tmp_path / "bad.json"
        m.write_text("not json")
        with pytest.raises(ValueError, match="JSON mal formatado"):
            rt.load_runtime_manifest(m)

    def test_wrong_schema_version(self, tmp_path):
        m = tmp_path / "wrong.json"
        m.write_text(json.dumps({"schemaVersion": 999, "targets": {}}))
        with pytest.raises(ValueError, match="schemaVersion"):
            rt.load_runtime_manifest(m)

    def test_missing_targets(self, tmp_path):
        m = tmp_path / "no_targets.json"
        m.write_text(json.dumps({"schemaVersion": 1}))
        with pytest.raises(ValueError, match="targets.*ausente"):
            rt.load_runtime_manifest(m)

    def test_empty_name_raises(self, tmp_path):
        m = tmp_path / "empty_name.json"
        m.write_text(json.dumps({
            "schemaVersion": 1,
            "targets": {
                "darwin-arm64": {
                    "backend": {"name": ""},
                    "scraper": {"name": "x"},
                },
            },
        }))
        with pytest.raises(ValueError, match="name.*invalido"):
            rt.load_runtime_manifest(m)

    def test_traversal_in_name_raises(self, tmp_path):
        m = tmp_path / "traversal.json"
        m.write_text(json.dumps({
            "schemaVersion": 1,
            "targets": {
                "darwin-arm64": {
                    "backend": {"name": "../../bin"},
                    "scraper": {"name": "x"},
                },
            },
        }))
        with pytest.raises(ValueError, match="traversal"):
            rt.load_runtime_manifest(m)

    def test_absolute_in_name_raises(self, tmp_path):
        m = tmp_path / "absolute.json"
        m.write_text(json.dumps({
            "schemaVersion": 1,
            "targets": {
                "darwin-arm64": {
                    "backend": {"name": "/absolute/path"},
                    "scraper": {"name": "x"},
                },
            },
        }))
        with pytest.raises(ValueError, match="absoluto"):
            rt.load_runtime_manifest(m)

    def test_white_space_name_raises(self, tmp_path):
        m = tmp_path / "whitespace.json"
        m.write_text(json.dumps({
            "schemaVersion": 1,
            "targets": {
                "darwin-arm64": {
                    "backend": {"name": "  "},
                    "scraper": {"name": "x"},
                },
            },
        }))
        with pytest.raises(ValueError, match="name.*invalido"):
            rt.load_runtime_manifest(m)


# ---------------------------------------------------------------------------
# target_configuration
# ---------------------------------------------------------------------------

class TestTargetConfiguration:
    def test_existing_target(self):
        manifest = {"targets": {"darwin-arm64": {"backend": {"name": "P"}, "scraper": {"name": "S"}}}}
        cfg = rt.target_configuration(manifest, "darwin-arm64")
        assert cfg["backend"]["name"] == "P"

    def test_missing_target_raises(self):
        manifest = {"targets": {"win32-x64": {"backend": {"name": "P"}, "scraper": {"name": "S"}}}}
        with pytest.raises(RuntimeError, match="nao suportado"):
            rt.target_configuration(manifest, "linux-arm64")


# ---------------------------------------------------------------------------
# resolve_resource
# ---------------------------------------------------------------------------

class TestResolveResource:
    def test_resolves_backend(self, tmp_path):
        manifest = {
            "targets": {
                "darwin-arm64": {
                    "backend": {"name": "ProspectOS"},
                    "scraper": {"name": "x"},
                },
            },
        }
        path = rt.resolve_resource(manifest, "darwin-arm64", "backend", tmp_path)
        assert path == tmp_path / "ProspectOS"

    def test_resolves_scraper(self, tmp_path):
        manifest = {
            "targets": {
                "darwin-arm64": {
                    "backend": {"name": "P"},
                    "scraper": {"name": "google-maps-scraper"},
                },
            },
        }
        path = rt.resolve_resource(manifest, "darwin-arm64", "scraper", tmp_path)
        assert path == tmp_path / "google-maps-scraper"

    def test_resolves_windows_exe(self, tmp_path):
        manifest = {
            "targets": {
                "win32-x64": {
                    "backend": {"name": "ProspectOS.exe"},
                    "scraper": {"name": "google-maps-scraper.exe"},
                },
            },
        }
        path = rt.resolve_resource(manifest, "win32-x64", "backend", tmp_path)
        assert path == tmp_path / "ProspectOS.exe"


# ---------------------------------------------------------------------------
# validate_executable
# ---------------------------------------------------------------------------

class TestValidateExecutable:
    def test_existing_executable_passes(self, tmp_path):
        exe = tmp_path / "executable"
        exe.write_text("fake binary")
        exe.chmod(0o755)
        rt.validate_executable(exe, "Backend")

    def test_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="nao encontrado"):
            rt.validate_executable(tmp_path / "nope", "X")

    def test_directory_raises(self, tmp_path):
        sub = tmp_path / "mydir"
        sub.mkdir()
        with pytest.raises(IsADirectoryError, match="diretorio"):
            rt.validate_executable(sub, "Dir")

    def test_no_exec_permission_raises_on_non_windows(self, tmp_path):
        if sys.platform == "win32":
            pytest.skip("permissoes POSIX nao se aplicam no Windows")
        exe = tmp_path / "noexec"
        exe.write_text("content")
        exe.chmod(0o644)
        with pytest.raises(PermissionError, match="permissao de execucao"):
            rt.validate_executable(exe, "Scraper")


# ---------------------------------------------------------------------------
# resolve_scraper (defaults)
# ---------------------------------------------------------------------------

class TestResolveScraper:
    def test_resolve_scraper_with_explicit_args(self, tmp_path):
        manifest = {
            "targets": {
                "darwin-arm64": {
                    "backend": {"name": "P"},
                    "scraper": {"name": "google-maps-scraper"},
                },
            },
        }
        path = rt.resolve_scraper(manifest=manifest, target="darwin-arm64", resource_root=tmp_path)
        assert path == tmp_path / "google-maps-scraper"

    def test_resolve_windows_scraper(self, tmp_path):
        manifest = {
            "targets": {
                "win32-x64": {
                    "backend": {"name": "P"},
                    "scraper": {"name": "google-maps-scraper.exe"},
                },
            },
        }
        path = rt.resolve_scraper(manifest=manifest, target="win32-x64", resource_root=tmp_path)
        assert path == tmp_path / "google-maps-scraper.exe"


# ---------------------------------------------------------------------------
# Integration: temp directory with fake executables
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_darwin_arm64_resolves_without_exe(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(rt._platform, "machine", lambda: "arm64")

        resources = tmp_path / "resources"
        resources.mkdir()
        (resources / "google-maps-scraper").write_text("fake")
        (resources / "google-maps-scraper").chmod(0o755)

        manifest_data = {
            "schemaVersion": 1,
            "targets": {
                "darwin-arm64": {
                    "backend": {"name": "ProspectOS"},
                    "scraper": {"name": "google-maps-scraper"},
                },
            },
        }
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data))

        manifest = rt.load_runtime_manifest(manifest_file)
        assert rt.current_target() == "darwin-arm64"
        scraper_path = rt.resolve_scraper(manifest=manifest, target="darwin-arm64", resource_root=resources)
        assert scraper_path == resources / "google-maps-scraper"

        rt.validate_executable(scraper_path, "Scraper")

    def test_win32_x64_resolves_with_exe(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(rt._platform, "machine", lambda: "AMD64")

        resources = tmp_path / "resources"
        resources.mkdir()
        (resources / "google-maps-scraper.exe").write_text("fake")

        manifest_data = {
            "schemaVersion": 1,
            "targets": {
                "win32-x64": {
                    "backend": {"name": "ProspectOS.exe"},
                    "scraper": {"name": "google-maps-scraper.exe"},
                },
            },
        }
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data))

        manifest = rt.load_runtime_manifest(manifest_file)
        assert rt.current_target() == "win32-x64"
        scraper_path = rt.resolve_scraper(manifest=manifest, target="win32-x64", resource_root=resources)
        assert scraper_path == resources / "google-maps-scraper.exe"
        assert str(scraper_path).endswith(".exe")

    def test_safe_join_stays_within_root(self, tmp_path):
        resources = tmp_path / "resources"
        resources.mkdir()

        result = rt.safe_join(resources, "backend/ProspectOS")
        assert str(result).startswith(str(resources.resolve()))

    def test_env_override_target(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PROSPECTOS_RUNTIME_TARGET", "win32-x64")
        target = os.environ.get("PROSPECTOS_RUNTIME_TARGET", rt.current_target())
        assert target == "win32-x64"

    def test_env_override_manifest(self, tmp_path, monkeypatch):
        manifest_data = {
            "schemaVersion": 1,
            "targets": {
                "darwin-arm64": {
                    "backend": {"name": "ProspectOS"},
                    "scraper": {"name": "google-maps-scraper"},
                },
            },
        }
        manifest_file = tmp_path / "override.json"
        manifest_file.write_text(json.dumps(manifest_data))
        monkeypatch.setenv("PROSPECTOS_RUNTIME_MANIFEST", str(manifest_file))

        from paths import DIR_RECURSOS
        env_path = os.environ.get("PROSPECTOS_RUNTIME_MANIFEST")
        manifest = rt.load_runtime_manifest(env_path)
        assert manifest["targets"]["darwin-arm64"]["backend"]["name"] == "ProspectOS"


# ---------------------------------------------------------------------------
# Contract parity test: JS and Python read the same file
# ---------------------------------------------------------------------------

class TestContractParity:
    def test_carrega_o_mesmo_json_do_repositorio(self):
        manifest_path = Path(__file__).parent.parent.parent / "shared" / "runtime-targets.json"
        assert manifest_path.exists(), f"Manifesto nao encontrado: {manifest_path}"
        manifest = rt.load_runtime_manifest(manifest_path)
        assert manifest["schemaVersion"] == 1
        targets = manifest["targets"]
        assert "darwin-arm64" in targets
        assert "darwin-x64" in targets
        assert "win32-x64" in targets
        assert "linux-x64" in targets
        for t_key, t_val in targets.items():
            assert "backend" in t_val
            assert "scraper" in t_val
            assert "name" in t_val["backend"]
            assert "name" in t_val["scraper"]
            assert t_val["backend"]["name"] != ""
            assert t_val["scraper"]["name"] != ""

    def test_darwin_arm64_sem_exe(self):
        manifest_path = Path(__file__).parent.parent.parent / "shared" / "runtime-targets.json"
        manifest = rt.load_runtime_manifest(manifest_path)
        be = manifest["targets"]["darwin-arm64"]["backend"]["name"]
        sc = manifest["targets"]["darwin-arm64"]["scraper"]["name"]
        assert not be.endswith(".exe"), f"darwin-arm64 backend nao deve ter .exe: {be}"
        assert not sc.endswith(".exe"), f"darwin-arm64 scraper nao deve ter .exe: {sc}"

    def test_win32_x64_com_exe(self):
        manifest_path = Path(__file__).parent.parent.parent / "shared" / "runtime-targets.json"
        manifest = rt.load_runtime_manifest(manifest_path)
        be = manifest["targets"]["win32-x64"]["backend"]["name"]
        sc = manifest["targets"]["win32-x64"]["scraper"]["name"]
        assert be.endswith(".exe"), f"win32-x64 backend deve ter .exe: {be}"
        assert sc.endswith(".exe"), f"win32-x64 scraper deve ter .exe: {sc}"

    def test_linux_x64_sem_exe(self):
        manifest_path = Path(__file__).parent.parent.parent / "shared" / "runtime-targets.json"
        manifest = rt.load_runtime_manifest(manifest_path)
        be = manifest["targets"]["linux-x64"]["backend"]["name"]
        sc = manifest["targets"]["linux-x64"]["scraper"]["name"]
        assert not be.endswith(".exe"), f"linux-x64 backend nao deve ter .exe: {be}"
        assert not sc.endswith(".exe"), f"linux-x64 scraper nao deve ter .exe: {sc}"
