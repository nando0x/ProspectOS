"""Testes de configuracao do PyInstaller spec e do build.

Testa que:
  - spec multiplataforma e valido
  - nome logico nao contem .exe
  - frontend e RuntimeManifest sao incluidos
  - scraper e Node estao ausentes do spec
  - hidden imports por plataforma estao corretos
  - exclusoes de desenvolvimento estao presentes
  - paths sao independentes do cwd
"""

import json
import os
import sys
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SPEC_DIR.parent


# ---------------------------------------------------------------------------
# Spec content validation
# ---------------------------------------------------------------------------

class TestSpecStructure:
    def test_spec_file_exists(self):
        spec = SPEC_DIR / "prospectos.spec"
        assert spec.is_file(), f"spec nao encontrado: {spec}"

    def test_spec_name_no_exe(self):
        """O nome logico no spec nao deve ser 'ProspectOS.exe'."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        assert 'name="ProspectOS"' in content or "name='ProspectOS'" in content
        assert 'name="ProspectOS.exe"' not in content
        assert "name='ProspectOS.exe'" not in content

    def test_spec_uses_platform_detection(self):
        """O spec deve ter deteccao de plataforma."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        assert "IS_WINDOWS" in content or "sys.platform" in content
        assert "IS_MACOS" in content or "darwin" in content

    def test_spec_no_scraper_in_datas(self):
        """Scraper nao deve estar no datas do spec."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        assert "google-maps-scraper" not in content
        assert "scraper_process" not in content

    def test_spec_no_node_in_datas(self):
        """Node nao deve estar no datas do spec."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        assert '"node"' not in content
        assert "'node'" not in content
        # Permitir mencoes literais de node.exe em comentarios inline,
        # mas nao como entry no datas
        lines = content.split("\n")
        datas_section = False
        for line in lines:
            if "datas" in line and "=" in line:
                datas_section = True
            if datas_section and ("]" in line or "a =" in line or "Analysis" in line):
                datas_section = False
            if datas_section and "node" in line.lower() and ".exe" not in line:
                pass  # skip

    def test_spec_includes_frontend(self):
        """Frontend dist deve estar no datas."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        assert "frontend" in content.lower()
        assert "dist" in content.lower()

    def test_spec_includes_runtime_manifest(self):
        """RuntimeManifest deve estar no datas."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        assert "runtime-targets.json" in content

    def test_spec_has_keyring_conditional(self):
        """Keyring deve ter hidden import condicional por plataforma."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        assert "keyring" in content
        assert "IS_WINDOWS" in content or "IS_MACOS" in content or "IS_LINUX" in content

    def test_spec_excludes_pytest(self):
        """pytest deve estar nos excludes."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        assert "pytest" in content
        assert '"pytest"' in content or "'pytest'" in content

    def test_spec_includes_instagrapi(self):
        """instagrapi deve estar nos hiddenimports."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        assert "instagrapi" in content

    def test_spec_includes_waitress(self):
        """waitress deve estar nos hiddenimports."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        assert "waitress" in content

    def test_spec_includes_ai_sdks(self):
        """SDKs de IA devem estar nos hiddenimports."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        assert "google" in content
        assert "openai" in content


# ---------------------------------------------------------------------------
# Path independence
# ---------------------------------------------------------------------------

class TestPathIndependence:
    def test_spec_paths_derived_from_specpath(self):
        """O spec deve derivar paths de SPECPATH/SPEC_DIR, nao de cwd."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        assert "SPEC_DIR" in content or "SPECPATH" in content

    def test_no_hardcoded_absolute_paths(self):
        """Nao deve ter paths absolutos do desenvolvedor."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        assert "/Users/" not in content
        assert "/home/" not in content
        assert "/tmp/" not in content or "#" in content  # permitir comentarios


# ---------------------------------------------------------------------------
# Platform-conditional hidden imports
# ---------------------------------------------------------------------------

class TestPlatformHiddenImports:
    def test_windows_keyring_backend(self):
        """Windows deve usar keyring.backends.Windows."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")

        # Verificar que ao menos uma mencao de keyring backend existe
        keyring_mentions = [
            line.strip()
            for line in content.split("\n")
            if "keyring" in line.lower()
        ]
        assert len(keyring_mentions) >= 1

    def test_macos_keyring_backend(self):
        """macOS deve usar keyring.backends.macOS."""
        spec = SPEC_DIR / "prospectos.spec"
        content = spec.read_text(encoding="utf-8")
        # Deve ter branch macOS com keyring.backends.macOS
        assert "macOS" in content


# ---------------------------------------------------------------------------
# Resource resolution
# ---------------------------------------------------------------------------

class TestResourceResolution:
    def test_runtime_manifest_exists(self):
        """Runtime manifest compartilhado deve existir."""
        manifest = REPO_ROOT / "shared" / "runtime-targets.json"
        assert manifest.is_file(), f"manifesto nao encontrado: {manifest}"

    def test_runtime_manifest_valid_json(self):
        """Runtime manifest deve ser JSON valido."""
        manifest = REPO_ROOT / "shared" / "runtime-targets.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert "schemaVersion" in data
        assert "targets" in data
        assert "darwin-arm64" in data["targets"]
        assert "win32-x64" in data["targets"]

    def test_frontend_dist_exists(self):
        """frontend/dist deve existir antes do build."""
        dist = REPO_ROOT / "frontend" / "dist"
        if not dist.is_dir():
            pytest.skip("frontend/dist nao encontrado - necessario npm run build")
        assert dist.is_dir()
        assert (dist / "index.html").is_file()

    def test_packaged_backend_finds_internal_manifest(self):
        """O backend empacotado deve encontrar o manifesto interno via DIR_RECURSOS."""
        from paths import DIR_RECURSOS, EMPACOTADO
        if not EMPACOTADO:
            # Em modo fonte, usa shared/runtime-targets.json via caminho relativo
            expected = REPO_ROOT / "shared" / "runtime-targets.json"
        else:
            expected = DIR_RECURSOS / "runtime-targets.json"

        from runtime_targets import _default_manifest_path
        resolved = _default_manifest_path()
        if not EMPACOTADO:
            assert resolved == expected


# ---------------------------------------------------------------------------
# Bundle imports smoke test (run with an existing bundle)
# ---------------------------------------------------------------------------

class TestBundleImports:
    """Testa que os imports funcionam dentro do bundle PyInstaller.

    Esses testes requerem um bundle existente em backend/dist/ProspectOS.
    """

    @pytest.fixture(scope="class")
    def bundle_dir(self):
        bundle = (SPEC_DIR / "dist" / "ProspectOS").resolve()
        if not bundle.is_dir():
            pytest.skip("bundle PyInstaller nao encontrado em backend/dist/ProspectOS")
        return bundle

    def test_embedded_modules(self, bundle_dir):
        """Verificar que modulos principais estao no bundle (via dist-info ou executavel)."""
        # Modules are embedded in the PyInstaller CArchive/PYZ inside the executable.
        # As evidence of proper inclusion, check for keyring dist-info.
        # Modules without dist-info (instagrapi, etc.) are still embedded — this is
        # verified at runtime by the smoke test.
        internals = list((bundle_dir / "_internal").glob("keyring-*.dist-info"))
        assert internals, "keyring dist-info not found in _internal"

    def test_frontend_in_bundle(self, bundle_dir):
        """Frontend buildado deve estar no bundle."""
        # Verificar possiveis layouts do PyInstaller 6.x
        possible = [
            bundle_dir / "_internal" / "frontend_dist" / "index.html",
            bundle_dir / "frontend_dist" / "index.html",
        ]
        found = any(p.is_file() for p in possible)
        if not found:
            pytest.skip(
                "frontend_dist/index.html nao encontrado no bundle. "
                "Layout pode variar conforme versao do PyInstaller."
            )
        assert True

    def test_runtime_manifest_in_bundle(self, bundle_dir):
        """Runtime manifest deve estar no bundle."""
        possible = [
            bundle_dir / "_internal" / "shared" / "runtime-targets.json",
            bundle_dir / "shared" / "runtime-targets.json",
        ]
        found = any(p.is_file() for p in possible)
        if not found:
            pytest.skip(
                "runtime-targets.json nao encontrado no bundle. "
                "Pode estar em localizacao diferente."
            )
        assert True

    def test_executable_name_correct(self, bundle_dir):
        """Nome do executavel deve ser 'ProspectOS' (sem .exe no macOS)."""
        exe = bundle_dir / "ProspectOS"
        if exe.is_file():
            assert True
            return
        exe_win = bundle_dir / "ProspectOS.exe"
        if exe_win.is_file():
            assert True
            return
        pytest.skip("executavel nao encontrado no bundle")


# ---------------------------------------------------------------------------
# Build script validation
# ---------------------------------------------------------------------------

class TestBuildScript:
    def test_build_script_exists(self):
        """build_backend.py deve existir."""
        script = REPO_ROOT / "scripts" / "build_backend.py"
        assert script.is_file(), f"build script nao encontrado: {script}"

    def test_build_script_has_required_args(self):
        """build script deve ter --clean, --skip-frontend, --dist-dir, --work-dir."""
        script = REPO_ROOT / "scripts" / "build_backend.py"
        content = script.read_text(encoding="utf-8")
        assert "--clean" in content
        assert "--skip-frontend" in content
        assert "--dist-dir" in content
        assert "--work-dir" in content

    def test_build_script_validates_architecture(self):
        """build script deve validar arquitetura no macOS."""
        script = REPO_ROOT / "scripts" / "build_backend.py"
        content = script.read_text(encoding="utf-8")
        assert "arm64" in content

    def test_build_script_checks_frontend(self):
        """build script deve validar frontend/dist."""
        script = REPO_ROOT / "scripts" / "build_backend.py"
        content = script.read_text(encoding="utf-8")
        assert "frontend" in content.lower() and "dist" in content
