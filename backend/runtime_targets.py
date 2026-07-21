"""Runtime binary targets for ProspectOS — resolve native binaries by platform+architecture.

Shared contract with desktop/runtime-target.js via shared/runtime-targets.json.
"""

import json
import logging
import os
import platform as _platform
import sys
from pathlib import Path

SCHEMA_VERSION = 1

SUPPORTED_TARGETS = frozenset((
    "darwin-arm64",
    "darwin-x64",
    "win32-x64",
    "linux-x64",
))

PLATFORM_MAP = {
    "darwin": "darwin",
    "win32": "win32",
    "linux": "linux",
}

ARCH_MAP = {
    "arm64": "arm64",
    "aarch64": "arm64",
    "x64": "x64",
    "amd64": "x64",
    "x86_64": "x64",
}

logger = logging.getLogger(__name__)


def normalize_platform(platform_str=None):
    if platform_str is None:
        platform_str = sys.platform
    return PLATFORM_MAP.get(platform_str)


def normalize_architecture(arch_str=None):
    arch_str = (arch_str or _platform.machine()).lower()
    return ARCH_MAP.get(arch_str)


def current_target():
    platform = normalize_platform()
    arch = normalize_architecture()
    if not platform or not arch:
        raise RuntimeError(
            f"Runtime target nao suportado: {sys.platform}-{_platform.machine()}"
        )
    return f"{platform}-{arch}"


def safe_join(root, relative_path):
    root = Path(root).absolute()

    if isinstance(relative_path, Path):
        relative_path = str(relative_path)

    if not relative_path:
        raise ValueError("Path relativo vazio nao e permitido")

    rp = Path(relative_path)
    if rp.is_absolute():
        raise ValueError(f"Path absoluto nao e permitido: {relative_path}")

    import re
    if re.match(r'^[a-zA-Z]:\\', relative_path):
        raise ValueError(f"Path absoluto nao e permitido: {relative_path}")

    normalized = rp.as_posix()
    if normalized.startswith(".."):
        raise ValueError(f"Path traversal detectado: {relative_path}")

    resolved = (root / rp).resolve()
    root_resolved = root.resolve()
    if not str(resolved).startswith(str(root_resolved)):
        raise ValueError(f"Path traversal detectado: {relative_path}")

    return resolved


def _validar_entry_name(name, target_key, resource_key):
    if not name or not isinstance(name, str) or name.strip() == "":
        raise ValueError(
            f"Runtime manifest invalido: target \"{target_key}\" "
            f"\"{resource_key}.name\" invalido"
        )
    name_stripped = name.strip()
    if ".." in name_stripped or Path(name_stripped).is_absolute():
        raise ValueError(
            f"Runtime manifest invalido: target \"{target_key}\" "
            f"\"{resource_key}.name\" contem path traversal ou path absoluto: {name}"
        )


def load_runtime_manifest(manifest_path):
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Runtime manifest nao encontrado: {manifest_path}"
        )

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Runtime manifest invalido (JSON mal formatado): {exc}"
        )

    if not isinstance(data, dict):
        raise ValueError("Runtime manifest invalido: esperado um objeto JSON")

    if data.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(
            f"Runtime manifest schemaVersion nao suportada: "
            f"{data.get('schemaVersion')}. Esperada: {SCHEMA_VERSION}"
        )

    targets = data.get("targets")
    if not isinstance(targets, dict):
        raise ValueError(
            "Runtime manifest invalido: campo 'targets' ausente ou invalido"
        )

    for target_key, target_val in targets.items():
        if not isinstance(target_val, dict):
            raise ValueError(
                f"Runtime manifest invalido: target "
                f"\"{target_key}\" nao e um objeto"
            )
        for resource in ("backend", "scraper"):
            entry = target_val.get(resource)
            if not isinstance(entry, dict):
                raise ValueError(
                    f"Runtime manifest invalido: target \"{target_key}\" "
                    f"nao possui \"{resource}\""
                )
            name = entry.get("name")
            _validar_entry_name(name, target_key, resource)

    return data


def target_configuration(manifest, target):
    if target not in manifest.get("targets", {}):
        raise RuntimeError(f"Runtime target nao suportado: {target}")
    return manifest["targets"][target]


def resolve_resource(manifest, target, resource_key, resource_root):
    cfg = target_configuration(manifest, target)
    entry = cfg.get(resource_key)
    if not entry:
        raise RuntimeError(
            f"Recurso \"{resource_key}\" nao encontrado no manifesto para {target}"
        )
    name = entry["name"]
    name = Path(name).name
    return safe_join(resource_root, name)


def resolve_scraper(manifest=None, target=None, resource_root=None):
    if manifest is None or target is None or resource_root is None:
        from paths import DIR_RECURSOS
        if manifest is None:
            manifest_path = _default_manifest_path()
            manifest = load_runtime_manifest(manifest_path)
        if target is None:
            target = current_target()
        if resource_root is None:
            resource_root = DIR_RECURSOS
    return resolve_resource(manifest, target, "scraper", resource_root)


def _default_manifest_path():
    from paths import DIR_RECURSOS
    env_path = os.environ.get("PROSPECTOS_RUNTIME_MANIFEST")
    if env_path:
        return Path(env_path)
    if getattr(sys, "frozen", False):
        return DIR_RECURSOS / "runtime-targets.json"
    return DIR_RECURSOS.parent / "shared" / "runtime-targets.json"


def validate_executable(file_path, label="Recurso"):
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(
            f"{label} nao encontrado: {file_path}"
        )
    if file_path.is_dir():
        raise IsADirectoryError(
            f"{label} e um diretorio, nao um executavel: {file_path}"
        )
    if sys.platform != "win32":
        if not os.access(str(file_path), os.X_OK):
            raise PermissionError(
                f"{label} nao possui permissao de execucao: {file_path}"
            )
