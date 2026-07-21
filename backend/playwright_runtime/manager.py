"""PlaywrightRuntimeManager — install, validate, diagnose, repair, and locate Playwright runtime."""

import json
import logging
import os
import shutil
import time
from pathlib import Path

from .errors import (
    PlaywrightRuntimeError,
    UnsupportedTargetError,
    SpecInvalidError,
    LockedError,
    DiskSpaceInsufficientError,
    CancelledError,
    IncompleteInstallationError,
    CorruptedInstallationError,
    NodeInvalidError,
    DriverInvalidError,
    BrowserInvalidError,
)
from .lock import InstallationLock
from .manifest import InstallationManifest
from .downloader import Downloader
from .extractor import safe_extract_tgz, safe_extract_tar
from .validator import (
    validate_is_file,
    validate_is_executable,
    validate_sha256,
    run_subprocess,
    check_architecture,
    validate_playwright_browsers_json,
    is_within_root,
)
from .models import (
    RuntimeState,
    RuntimeInspection,
    RuntimeInstallation,
    RuntimeValidation,
    RuntimeDiagnostics,
    ComponentInfo,
    ProgressStage,
    ProgressEvent,
)

logger = logging.getLogger(__name__)

_MINIMUM_SPACE_REQUIRED = 2.5 * 1024 ** 3  # 2.5 GB
_MINIMUM_SPACE_LABEL = "2.5 GB"


def _get_shared_manifest_path():
    """Locate the shared playwright-runtime-targets.json."""
    env_path = os.environ.get("PROSPECTOS_PLAYWRIGHT_RUNTIME_MANIFEST")
    if env_path:
        return Path(env_path)
    this_dir = Path(__file__).parent
    backend_dir = this_dir.parent
    shared_path = backend_dir.parent / "shared" / "playwright-runtime-targets.json"
    if shared_path.exists():
        return shared_path
    return backend_dir.parent.parent / "shared" / "playwright-runtime-targets.json"


class PlaywrightRuntimeManager:
    """Manages the Playwright runtime: install, validate, diagnose, repair, remove."""

    def __init__(
        self,
        cache_root: Path | None = None,
        target: str | None = None,
        spec_path: Path | None = None,
        http_client=None,
        subprocess_runner=None,
        clock=None,
    ):
        from paths import DIR_CACHE

        self._cache_root = (cache_root or DIR_CACHE).resolve()
        self._target = target or self._resolve_target()
        self._spec_path = spec_path or _get_shared_manifest_path()
        self._http_client = http_client
        self._subprocess_runner = subprocess_runner or run_subprocess
        self._clock = clock or time

        self._runtime_root = self._cache_root / "playwright"
        self._downloads_dir = self._runtime_root / "downloads"
        self._staging_dir = self._runtime_root / "staging"
        self._installations_dir = self._runtime_root / "installations"
        self._locks_dir = self._runtime_root / "locks"
        self._diagnostics_dir = self._runtime_root / "diagnostics"

        self._spec = self._load_spec()
        if self._target not in self._spec.get("runtimes", {}):
            raise UnsupportedTargetError(self._target)

        self._runtime_spec = self._spec["runtimes"][self._target]
        self._runtime_id = self._runtime_spec["runtimeId"]
        self._installation_dir = self._installations_dir / self._target / self._runtime_id
        self._manifest = InstallationManifest(self._installation_dir)
        self._downloader = Downloader(self._downloads_dir, http_client=http_client)
        self._lock = InstallationLock(self._locks_dir, self._target, self._runtime_id)

    # ── public API ─────────────────────────────────────────────────────

    def inspect(self) -> RuntimeInspection:
        state = self._determine_state()
        components = {}
        spec = self._runtime_spec

        if state == RuntimeState.READY:
            components = self._get_component_info()

        insp = RuntimeInspection(
            state=state,
            runtime_id=self._runtime_id,
            target=self._target,
            root=str(self._runtime_root),
            components=components,
        )

        if state == RuntimeState.UNSUPPORTED:
            insp.details = f"Target {self._target} nao possui spec"
        elif state == RuntimeState.NOT_INSTALLED:
            insp.details = "Nenhuma instalacao encontrada"
        elif state == RuntimeState.INCOMPLETE:
            insp.details = "Instalacao incompleta"
            insp.errors = self._find_missing_components()
        elif state == RuntimeState.CORRUPTED:
            insp.details = "Instalacao corrompida"
            insp.errors = self._find_corrupted_components()

        return insp

    def is_ready(self) -> bool:
        return self._quick_validation()

    def install(self, progress=None, cancel=None) -> RuntimeInstallation:
        if self.is_ready():
            raise PlaywrightRuntimeError(
                code="PLAYWRIGHT_RUNTIME_READY",
                message="Runtime ja esta pronto e validado",
                suggestion="Use repair() se precisar reinstalar",
            )

        return self._install(progress=progress, cancel=cancel)

    def ensure_ready(self, progress=None, cancel=None) -> RuntimeInstallation:
        state = self._determine_state()
        if state == RuntimeState.READY:
            return RuntimeInstallation(
                success=True,
                runtime_id=self._runtime_id,
                target=self._target,
                path=str(self._installation_dir),
                state=RuntimeState.READY,
            )

        if state == RuntimeState.UNSUPPORTED:
            raise UnsupportedTargetError(self._target)

        if state in (RuntimeState.INCOMPLETE, RuntimeState.CORRUPTED):
            return self.repair(progress=progress, cancel=cancel)

        return self._install(progress=progress, cancel=cancel)

    def validate(self, quick: bool = True) -> RuntimeValidation:
        errors = []
        warnings = []
        component_versions = {}

        if not self._installation_dir.exists():
            return RuntimeValidation(
                valid=False, runtime_id=self._runtime_id, target=self._target,
                quick=quick, errors=["Diretorio de instalacao nao existe"],
            )

        if not self._manifest.exists():
            return RuntimeValidation(
                valid=False, runtime_id=self._runtime_id, target=self._target,
                quick=quick, errors=["Manifesto de instalacao nao encontrado"],
            )

        manifest = self._manifest.read()
        if not manifest:
            return RuntimeValidation(
                valid=False, runtime_id=self._runtime_id, target=self._target,
                quick=quick, errors=["Manifesto de instalacao invalido"],
            )

        if manifest.get("status") != "ready":
            errors.append(f"Status do manifesto: {manifest.get('status')}")

        if not self._manifest.matches_target(self._target):
            errors.append(f"Target do manifesto nao corresponde: {manifest.get('platform')} != {self._target}")

        if not self._manifest.matches_runtime_id(self._runtime_id):
            errors.append(f"Runtime ID nao corresponde: {manifest.get('runtimeId')} != {self._runtime_id}")

        driver_dir = self._installation_dir / "driver"
        browsers_dir = self._installation_dir / "browsers"

        node_path = driver_dir / "node"
        cli_path = driver_dir / "package" / "cli.js"

        # Validate Node
        if not validate_is_executable(node_path, "Node"):
            errors.append("Node nao encontrado ou sem permissao de execucao")
        else:
            versions = self._get_node_version(node_path)
            if versions and "node_version" in versions:
                component_versions["node"] = versions["node_version"]
            if quick:
                # quick: just check existence and basic version
                pass
            else:
                # full: compare version exactly
                node_spec = self._runtime_spec.get("node", {})
                expected_ver = node_spec.get("version", "")
                if expected_ver and component_versions.get("node") != f"v{expected_ver}":
                    errors.append(f"Versao do Node: esperada v{expected_ver}, obtida {component_versions.get('node')}")

        # Validate playwright-core
        if not validate_is_file(cli_path, "Playwright CLI"):
            errors.append("playwright-core/cli.js nao encontrado")
        else:
            versions = self._get_playwright_version(node_path, cli_path)
            if versions:
                component_versions["playwright"] = versions.get("playwright_version", "")
            if not quick:
                pw_spec = self._runtime_spec.get("playwright", {})
                expected_pw = pw_spec.get("driverVersion", "")
                if expected_pw and component_versions.get("playwright") != expected_pw:
                    errors.append(f"Versao do Playwright: esperada {expected_pw}, obtida {component_versions.get('playwright')}")

        # Validate browsers
        if not browsers_dir.exists():
            errors.append("Diretorio de browsers nao existe")
        else:
            expected_browsers = self._runtime_spec.get("browsers", {})

            for browser_key in ("chromium", "headlessShell", "ffmpeg"):
                browser_info = expected_browsers.get(browser_key, {})
                revision = browser_info.get("revision")
                dir_name = self._browser_dir_name(browser_key)
                browser_path = browsers_dir / f"{dir_name}-{revision}"
                if not browser_path.exists():
                    browser_alt = self._find_browser_dir(browsers_dir, browser_key, revision)
                    if not browser_alt:
                        errors.append(f"Browser {browser_key} nao encontrado")
                    else:
                        browser_path = browser_alt

                if quick:
                    pass

            mapped_expected = {}
            for key, browser_info in expected_browsers.items():
                json_name = self._browser_json_name(key)
                mapped_expected[json_name] = browser_info
            browser_errors = validate_playwright_browsers_json(self._installation_dir, mapped_expected)
            errors.extend(browser_errors)

        # Architecture check (quick)
        if not quick and sys.platform != "win32":
            for binary_name, label in [("node", "Node"), (str(cli_path), "Playwright CLI")]:
                bp = Path(binary_name) if Path(binary_name).is_absolute() else node_path if binary_name == "node" else cli_path
                if bp.exists():
                    ok, arch_msg = check_architecture(bp, "arm64" if "arm64" in self._target else "x64")
                    if not ok:
                        warnings.append(f"{label}: {arch_msg}")

        valid = len(errors) == 0

        return RuntimeValidation(
            valid=valid,
            runtime_id=self._runtime_id,
            target=self._target,
            quick=quick,
            errors=errors,
            warnings=warnings,
            component_versions=component_versions,
        )

    def repair(self, progress=None, cancel=None) -> RuntimeInstallation:
        old_installation = None
        if self._installation_dir.exists() and self._quick_validation():
            old_installation = self._installation_dir
            logger.info("Instalacao atual valida, sera substituida apos nova instalacao pronta")

        staging_path = self._staging_dir / self._runtime_id
        if staging_path.exists():
            shutil.rmtree(staging_path, ignore_errors=True)

        try:
            result = self._install(progress=progress, cancel=cancel, force=True)

            if result.success and old_installation and old_installation.exists():
                backup_path = old_installation.parent / f"{self._runtime_id}.bak"
                if backup_path.exists():
                    shutil.rmtree(backup_path, ignore_errors=True)
                old_installation.rename(backup_path)
                shutil.rmtree(backup_path, ignore_errors=True)

            return result
        except Exception:
            if old_installation and old_installation.exists():
                logger.info("Instalacao anterior preservada apos falha no reparo")
            raise

    def get_environment(self) -> dict[str, str]:
        driver_path = self._installation_dir / "driver"
        browsers_path = self._installation_dir / "browsers"
        return {
            "PLAYWRIGHT_DRIVER_PATH": str(driver_path),
            "PLAYWRIGHT_BROWSERS_PATH": str(browsers_path),
        }

    def get_diagnostics(self) -> RuntimeDiagnostics:
        try:
            free_bytes = shutil.disk_usage(self._runtime_root).free
        except OSError:
            free_bytes = 0

        manifest_data = self._manifest.read()
        component_versions = {}
        component_paths = {}
        for name, info in self._get_component_info().items():
            component_versions[name] = info.version
            component_paths[name] = info.path

        val = self.validate(quick=True)

        return RuntimeDiagnostics(
            target=self._target,
            runtime_id=self._runtime_id,
            state=self._determine_state().value,
            root=str(self._runtime_root),
            free_disk_bytes=free_bytes,
            locked=self._lock.is_locked(),
            manifest=manifest_data,
            component_versions=component_versions,
            component_paths=component_paths,
            last_validation=manifest_data.get("validatedAt", "") if manifest_data else "",
            validation_errors=val.errors,
        )

    def remove(self) -> None:
        target_root = self._installations_dir / self._target

        resolved = target_root.resolve()
        runtime_root_resolved = self._runtime_root.resolve()

        if str(resolved).strip() in ("/", str(Path.home()), str(Path("~").resolve())):
            raise PlaywrightRuntimeError(
                code="PLAYWRIGHT_RUNTIME_SECURITY",
                message=f"Protecao contra remocao de diretorio critico: {resolved}",
            )

        if resolved == runtime_root_resolved:
            raise PlaywrightRuntimeError(
                code="PLAYWRIGHT_RUNTIME_SECURITY",
                message="Nao e possivel remover a raiz do runtime",
            )

        try:
            resolved.relative_to(runtime_root_resolved)
        except ValueError:
            raise PlaywrightRuntimeError(
                code="PLAYWRIGHT_RUNTIME_SECURITY",
                message=f"Path fora da raiz do runtime: {resolved}",
            )

        if not target_root.exists():
            logger.info("Nada a remover para %s", self._target)
            return

        shutil.rmtree(target_root, ignore_errors=True)
        logger.info("Runtime removido: %s", target_root)

    # ── internal ───────────────────────────────────────────────────────

    def _resolve_target(self):
        env_target = os.environ.get("PROSPECTOS_RUNTIME_TARGET")
        if env_target:
            return env_target
        try:
            import runtime_targets as rt
            return rt.current_target()
        except Exception:
            import platform as _platform
            import sys
            plat = {"darwin": "darwin", "win32": "win32", "linux": "linux"}.get(sys.platform, "unknown")
            arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "amd64": "x64"}.get(_platform.machine().lower(), "unknown")
            return f"{plat}-{arch}"

    def _load_spec(self):
        spec_path = Path(self._spec_path) if isinstance(self._spec_path, str) else self._spec_path
        if not spec_path.exists():
            raise SpecInvalidError(detail=f"Arquivo nao encontrado: {spec_path}")
        try:
            data = json.loads(spec_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise SpecInvalidError(detail=str(e))

        if not isinstance(data, dict):
            raise SpecInvalidError(detail="Esperado um objeto JSON")
        if data.get("schemaVersion") != 1:
            raise SpecInvalidError(detail=f"schemaVersion: {data.get('schemaVersion')}")
        if "runtimes" not in data:
            raise SpecInvalidError(detail="Campo 'runtimes' ausente")
        return data

    def _determine_state(self):
        if self._target not in self._spec.get("runtimes", {}):
            return RuntimeState.UNSUPPORTED

        if self._lock.is_locked():
            return RuntimeState.DOWNLOADING

        if not self._installation_dir.exists():
            return RuntimeState.NOT_INSTALLED

        if not self._manifest.exists():
            return RuntimeState.INCOMPLETE

        manifest = self._manifest.read()
        if not manifest:
            return RuntimeState.CORRUPTED

        status = manifest.get("status")
        if status == "ready":
            if self._quick_validation():
                return RuntimeState.READY
            return RuntimeState.CORRUPTED

        return RuntimeState.INCOMPLETE

    def _quick_validation(self) -> bool:
        if not self._installation_dir.exists():
            return False
        if not self._manifest.exists():
            return False
        manifest = self._manifest.read()
        if not manifest:
            return False
        if manifest.get("status") != "ready":
            return False
        if not self._manifest.matches_target(self._target):
            return False
        if not self._manifest.matches_runtime_id(self._runtime_id):
            return False

        driver_dir = self._installation_dir / "driver"
        browsers_dir = self._installation_dir / "browsers"

        node_path = driver_dir / "node"
        if not validate_is_executable(node_path, "Node"):
            return False

        cli_path = driver_dir / "package" / "cli.js"
        if not validate_is_file(cli_path, "Playwright CLI"):
            return False

        if not browsers_dir.exists():
            return False

        expected_browsers = self._runtime_spec.get("browsers", {})
        for browser_name in ("chromium", "headlessShell", "ffmpeg"):
            browser_info = expected_browsers.get(browser_name, {})
            revision = browser_info.get("revision")
            dir_name = self._browser_dir_name(browser_name)
            browser_path = browsers_dir / f"{dir_name}-{revision}"
            if not browser_path.exists():
                alt = self._find_browser_dir(browsers_dir, browser_name, revision)
                if not alt:
                    return False

        if not is_within_root(self._installation_dir, self._runtime_root):
            return False

        return True

    @staticmethod
    def _browser_dir_name(browser_key: str) -> str:
        _dir_map = {
            "chromium": "chromium",
            "headlessShell": "chromium_headless_shell",
            "ffmpeg": "ffmpeg",
        }
        return _dir_map.get(browser_key, browser_key)

    @staticmethod
    def _browser_json_name(browser_key: str) -> str:
        _json_map = {
            "chromium": "chromium",
            "headlessShell": "chromium-headless-shell",
            "ffmpeg": "ffmpeg",
        }
        return _json_map.get(browser_key, browser_key)

    def _find_browser_dir(self, browsers_dir: Path, browser_name: str, revision) -> Path | None:
        pw_name = self._browser_dir_name(browser_name)
        prefix = f"{pw_name}-"
        for p in browsers_dir.iterdir():
            if p.is_dir() and p.name.startswith(prefix):
                return p
        return None

    def _find_missing_components(self) -> list[str]:
        missing = []
        driver_dir = self._installation_dir / "driver"
        browsers_dir = self._installation_dir / "browsers"

        if not (driver_dir / "node").exists():
            missing.append("node")
        if not (driver_dir / "package" / "cli.js").exists():
            missing.append("playwright-core/cli.js")

        expected_browsers = self._runtime_spec.get("browsers", {})
        for browser_key in ("chromium", "headlessShell", "ffmpeg"):
            browser_info = expected_browsers.get(browser_key, {})
            revision = browser_info.get("revision")
            dir_name = self._browser_dir_name(browser_key)
            if not (browsers_dir / f"{dir_name}-{revision}").exists():
                if not self._find_browser_dir(browsers_dir, browser_key, revision):
                    missing.append(browser_key)

        return missing

    def _find_corrupted_components(self) -> list[str]:
        corrupted = []
        manifest = self._manifest.read()
        if not manifest:
            return ["manifesto ausente"]

        comps = manifest.get("components", {})
        for name, info in comps.items():
            path_str = info.get("path", "")
            if not path_str:
                continue
            comp_path = self._installation_dir / path_str
            if not comp_path.exists():
                corrupted.append(f"{name}: {path_str} ausente")
            elif info.get("sha256"):
                if not validate_sha256(comp_path, info["sha256"]):
                    corrupted.append(f"{name}: sha256 nao confere")

        return corrupted

    def _get_component_info(self) -> dict[str, ComponentInfo]:
        result = {}
        manifest = self._manifest.read()
        if not manifest:
            return result

        comps = manifest.get("components", {})
        for name, info in comps.items():
            result[name] = ComponentInfo(
                version=info.get("version", ""),
                sha256=info.get("sha256", ""),
                source=info.get("source", ""),
                path=info.get("path", ""),
                architecture=info.get("architecture", ""),
                exists=(self._installation_dir / info.get("path", "")).exists() if info.get("path") else False,
            )

        return result

    def _get_node_version(self, node_path: Path) -> dict:
        rc, out, err = self._subprocess_runner([str(node_path), "--version"])
        if rc == 0:
            return {"node_version": out.strip()}
        return {}

    def _get_playwright_version(self, node_path: Path, cli_path: Path) -> dict:
        rc, out, err = self._subprocess_runner([str(node_path), str(cli_path), "--version"])
        if rc == 0:
            return {"playwright_version": out.strip()}
        return {}

    def _check_disk_space(self):
        try:
            usage = shutil.disk_usage(self._runtime_root)
            if usage.free < _MINIMUM_SPACE_REQUIRED:
                raise DiskSpaceInsufficientError(
                    available=usage.free,
                    required=_MINIMUM_SPACE_REQUIRED,
                    path_obj=self._runtime_root,
                )
        except OSError:
            pass

    def _install(self, progress=None, cancel=None, force=False) -> RuntimeInstallation:
        start_time = self._clock.time()

        if force is False and self.is_ready():
            raise PlaywrightRuntimeError(
                code="PLAYWRIGHT_RUNTIME_READY",
                message="Runtime ja esta pronto. Use force=True ou repair() para reinstalar.",
            )

        if cancel and cancel():
            raise CancelledError(stage="install")

        self._check_disk_space()

        staging_path = self._staging_dir / self._runtime_id
        if staging_path.exists():
            shutil.rmtree(staging_path, ignore_errors=True)
        staging_path.mkdir(parents=True, exist_ok=True)

        driver_staging = staging_path / "driver"
        browsers_staging = staging_path / "browsers"
        licenses_staging = staging_path / "licenses"

        try:
            with self._lock:
                if cancel and cancel():
                    raise CancelledError(stage="lock-acquired")

                self._fire_progress(progress, ProgressStage.DOWNLOADING_PLAYWRIGHT_CORE)

                pw_spec = self._runtime_spec["playwrightCore"]
                pw_result = self._downloader.download(
                    url=pw_spec["url"],
                    expected_sha256=pw_spec["sha256"],
                    archive_name=pw_spec["archive"],
                    progress=progress,
                    cancel=cancel,
                )

                if cancel and cancel():
                    raise CancelledError(stage="after-pw-download")

                self._fire_progress(progress, ProgressStage.DOWNLOADING_NODE)

                node_spec = self._runtime_spec["node"]
                node_result = self._downloader.download(
                    url=node_spec["url"],
                    expected_sha256=node_spec["sha256"],
                    archive_name=node_spec["archive"],
                    progress=progress,
                    cancel=cancel,
                )

                if cancel and cancel():
                    raise CancelledError(stage="after-node-download")

                self._fire_progress(progress, ProgressStage.VERIFYING_DOWNLOADS)

                self._fire_progress(progress, ProgressStage.EXTRACTING_PLAYWRIGHT_CORE)
                safe_extract_tgz(pw_result.path, driver_staging / "package_src")

                if cancel and cancel():
                    raise CancelledError(stage="after-pw-extract")

                self._fire_progress(progress, ProgressStage.EXTRACTING_NODE)
                safe_extract_tgz(node_result.path, driver_staging / "node_src")

                if cancel and cancel():
                    raise CancelledError(stage="after-node-extract")

                self._fire_progress(progress, ProgressStage.ASSEMBLING_DRIVER)

                self._assemble_driver(driver_staging, node_result.path)

                if cancel and cancel():
                    raise CancelledError(stage="after-driver-assembly")

                self._fire_progress(progress, ProgressStage.VALIDATING_DRIVER)
                self._validate_driver(driver_staging)

                self._fire_progress(progress, ProgressStage.INSTALLING_BROWSER)
                self._install_browsers(driver_staging, browsers_staging, progress, cancel)

                if cancel and cancel():
                    raise CancelledError(stage="after-browser-install")

                self._fire_progress(progress, ProgressStage.VALIDATING_BROWSER)
                self._validate_browsers(browsers_staging)

                self._copy_licenses(self._runtime_spec, licenses_staging)

                self._fire_progress(progress, ProgressStage.PUBLISHING)
                self._publish(staging_path)

                self._fire_progress(progress, ProgressStage.READY)

            duration = self._clock.time() - start_time

            return RuntimeInstallation(
                success=True,
                runtime_id=self._runtime_id,
                target=self._target,
                path=str(self._installation_dir),
                state=RuntimeState.READY,
                duration_seconds=duration,
            )

        except (PlaywrightRuntimeError, CancelledError):
            self._cleanup_staging(staging_path)
            raise
        except Exception as e:
            self._cleanup_staging(staging_path)
            raise PlaywrightRuntimeError(
                code="PLAYWRIGHT_RUNTIME_INSTALL_FAILED",
                message=f"Falha na instalacao: {e}",
                cause=str(e),
            ) from e

    def _assemble_driver(self, driver_staging: Path, node_archive_path: Path):
        """Assemble the driver from extracted Node and playwright-core."""
        driver_dir = driver_staging

        node_src = driver_staging / "node_src"
        package_src = driver_staging / "package_src"

        bin_dirs = list(node_src.glob("*/bin"))
        if bin_dirs:
            node_bin = bin_dirs[0]
        else:
            node_bin = node_src

        node_exe = node_bin / "node"
        if not node_exe.exists():
            alt = list(node_src.rglob("bin/node"))
            if alt:
                node_exe = alt[0]
            else:
                raise NodeInvalidError(detail="node binario nao encontrado apos extracao")

        driver_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(node_exe), str(driver_dir / "node"))
        os.chmod(str(driver_dir / "node"), 0o755)

        package_dir = driver_dir / "package"
        package_dir.mkdir(parents=True, exist_ok=True)

        package_contents = package_src / "package"
        if package_contents.exists():
            for item in package_contents.iterdir():
                dest = package_dir / item.name
                if item.is_dir():
                    shutil.copytree(str(item), str(dest), dirs_exist_ok=True)
                else:
                    shutil.copy2(str(item), str(dest))
        else:
            for item in package_src.iterdir():
                dest = package_dir / item.name
                if item.is_dir():
                    shutil.copytree(str(item), str(dest), dirs_exist_ok=True)
                else:
                    shutil.copy2(str(item), str(dest))

        shutil.rmtree(driver_staging / "node_src", ignore_errors=True)
        shutil.rmtree(driver_staging / "package_src", ignore_errors=True)

    def _validate_driver(self, driver_dir: Path):
        node_path = driver_dir / "node"
        if not validate_is_executable(node_path, "Node"):
            raise NodeInvalidError(detail="node nao encontrado ou sem permissao")

        cli_path = driver_dir / "package" / "cli.js"
        if not validate_is_file(cli_path, "Playwright CLI"):
            raise DriverInvalidError(detail="cli.js nao encontrado")

        rc, out, err = self._subprocess_runner([str(node_path), "--version"])
        if rc != 0:
            raise NodeInvalidError(detail=f"node --version falhou: {err}")

        expected_version = self._runtime_spec["node"]["version"]
        if f"v{expected_version}" not in out:
            raise NodeInvalidError(detail=f"versao do node: esperada v{expected_version}, obtida {out.strip()}")

        rc, out, err = self._subprocess_runner([str(node_path), str(cli_path), "--version"])
        if rc != 0:
            raise DriverInvalidError(detail=f"cli.js --version falhou: {err}")

        expected_pw = self._runtime_spec["playwright"]["driverVersion"]
        if expected_pw not in out:
            raise DriverInvalidError(detail=f"versao do playwright: esperada {expected_pw}, obtida {out.strip()}")

    def _install_browsers(self, driver_dir: Path, browsers_dir: Path, progress=None, cancel=None):
        node_path = driver_dir / "node"
        cli_path = driver_dir / "package" / "cli.js"

        env = os.environ.copy()
        env["HOME"] = str(self._staging_dir / ".home")
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)

        Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
        browsers_dir.mkdir(parents=True, exist_ok=True)

        cmd = [str(node_path), str(cli_path), "install", "chromium"]
        rc, out, err = self._subprocess_runner(cmd, env=env, timeout=600)

        if rc != 0:
            raise BrowserInstallFailedError(browser="chromium", exit_code=rc, stderr=err[:2000] if err else "")

    def _validate_browsers(self, browsers_dir: Path):
        expected = self._runtime_spec.get("browsers", {})

        for browser_key in ("chromium", "headlessShell", "ffmpeg"):
            browser_info = expected.get(browser_key, {})
            revision = browser_info.get("revision")
            dir_name = self._browser_dir_name(browser_key)
            browser_path = browsers_dir / f"{dir_name}-{revision}"
            if not browser_path.exists():
                alt = self._find_browser_dir(browsers_dir, browser_key, revision)
                if not alt:
                    raise BrowserInvalidError(browser=browser_key, detail=f"diretorio nao encontrado (revision {revision})")

    def _copy_licenses(self, spec: dict, licenses_dir: Path):
        licenses_dir.mkdir(parents=True, exist_ok=True)
        license_info = spec.get("licenses", {})

        for component_name, lic_type in license_info.items():
            notice_file = licenses_dir / f"{component_name}.txt"
            notice_file.write_text(
                f"{component_name}\n"
                f"License: {lic_type}\n"
                f"Part of ProspectOS managed Playwright runtime ({self._runtime_id})\n"
                f"See: https://github.com/microsoft/playwright (Playwright)\n"
                f"     https://nodejs.org (Node.js)\n"
                f"     https://www.chromium.org (Chromium)\n"
                f"     https://ffmpeg.org (FFmpeg)\n",
                encoding="utf-8",
            )

    def _publish(self, staging_path: Path):
        target_dir = self._installations_dir / self._target
        target_dir.mkdir(parents=True, exist_ok=True)

        final_dir = target_dir / self._runtime_id

        if final_dir.exists():
            shutil.rmtree(final_dir, ignore_errors=True)

        staging_path.rename(final_dir)

        self._installation_dir = final_dir
        self._manifest = InstallationManifest(final_dir)

        components = self._build_components_dict()
        self._manifest.write(
            runtime_id=self._runtime_id,
            target=self._target,
            status="ready",
            components=components,
        )

    def _build_components_dict(self) -> dict:
        spec = self._runtime_spec
        components = {}

        components["playwrightCore"] = {
            "version": spec.get("playwright", {}).get("coreVersion", ""),
            "sha256": spec.get("playwrightCore", {}).get("sha256", ""),
            "source": "npm registry",
            "path": "driver/package",
        }

        components["node"] = {
            "version": spec.get("node", {}).get("version", ""),
            "sha256": spec.get("node", {}).get("sha256", ""),
            "architecture": "arm64" if "arm64" in self._target else "x64",
            "source": "nodejs.org",
            "path": "driver/node",
        }

        browsers = spec.get("browsers", {})
        for browser_name in ("chromium", "headlessShell", "ffmpeg"):
            browser_info = browsers.get(browser_name, {})
            revision = browser_info.get("revision", "")
            components[browser_name] = {
                "version": browser_info.get("expectedVersion", str(revision)),
                "revision": revision,
                "path": f"browsers/{browser_name}-{revision}",
            }

        return components

    def _cleanup_staging(self, staging_path: Path):
        if staging_path.exists():
            shutil.rmtree(staging_path, ignore_errors=True)

    @staticmethod
    def _fire_progress(progress, stage: ProgressStage, **kw):
        if progress:
            event = ProgressEvent(stage=stage, **kw)
            progress(event.to_dict() if hasattr(progress, '__dict__') else event)
