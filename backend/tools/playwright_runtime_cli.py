"""CLI tool for Playwright runtime management.

Usage:
    python -m backend.tools.playwright_runtime_cli inspect
    python -m backend.tools.playwright_runtime_cli install
    python -m backend.tools.playwright_runtime_cli validate [--quick] [--full]
    python -m backend.tools.playwright_runtime_cli repair
    python -m backend.tools.playwright_runtime_cli diagnostics [--json]
    python -m backend.tools.playwright_runtime_cli remove [--yes]
    python -m backend.tools.playwright_runtime_cli env

Options:
    --cache-dir PATH    Override cache directory (or PROSPECTOS_CACHE_DIR)
    --target TARGET     Override target platform (or PROSPECTOS_RUNTIME_TARGET)
    --json              Output as JSON
    --quick             Quick validation (default)
    --full              Full validation (with checksums)
    --yes               Skip confirmation for remove

Exit codes:
    0 = success
    1 = general error
    2 = runtime invalid
    3 = unsupported target
    4 = download/checksum error
    5 = lock error
    6 = cancellation
"""

import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("playwright-runtime-cli")


def get_manager(args):
    from playwright_runtime.manager import PlaywrightRuntimeManager

    cache_dir = None
    if args.get("--cache-dir"):
        cache_dir = Path(args["--cache-dir"])
    elif os.environ.get("PROSPECTOS_CACHE_DIR"):
        cache_dir = Path(os.environ["PROSPECTOS_CACHE_DIR"])

    target = None
    if args.get("--target"):
        target = args["--target"]
    elif os.environ.get("PROSPECTOS_RUNTIME_TARGET"):
        target = os.environ["PROSPECTOS_RUNTIME_TARGET"]

    return PlaywrightRuntimeManager(cache_root=cache_dir, target=target)


def cmd_inspect(manager, args):
    inspection = manager.inspect()
    if args.get("--json"):
        print(json.dumps(inspection.to_dict(), indent=2))
    else:
        print(f"State: {inspection.state.value}")
        print(f"Runtime ID: {inspection.runtime_id}")
        print(f"Target: {inspection.target}")
        print(f"Root: {inspection.root}")
        if inspection.errors:
            print("Errors:")
            for e in inspection.errors:
                print(f"  - {e}")
        if inspection.details:
            print(f"Details: {inspection.details}")

    if inspection.state.value in ("corrupted", "incomplete"):
        sys.exit(2)
    elif inspection.state.value == "unsupported":
        sys.exit(3)


def cmd_install(manager, args):
    result = manager.install()
    if args.get("--json"):
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Installation {'succeeded' if result.success else 'failed'}: {result.runtime_id}")
        print(f"Path: {result.path}")
        print(f"Duration: {result.duration_seconds:.1f}s")

    if not result.success:
        sys.exit(1)


def cmd_validate(manager, args):
    quick = args.get("--quick", True) and not args.get("--full", False)
    result = manager.validate(quick=quick)
    if args.get("--json"):
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Validation: {'PASS' if result.valid else 'FAIL'}")
        print(f"Runtime ID: {result.runtime_id}")
        print(f"Target: {result.target}")
        print(f"Mode: {'quick' if quick else 'full'}")
        if result.component_versions:
            print("Versions:")
            for k, v in result.component_versions.items():
                print(f"  {k}: {v}")
        if result.errors:
            print("Errors:")
            for e in result.errors:
                print(f"  - {e}")
        if result.warnings:
            print("Warnings:")
            for w in result.warnings:
                print(f"  - {w}")

    if not result.valid:
        sys.exit(2)


def cmd_repair(manager, args):
    result = manager.repair()
    if args.get("--json"):
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Repair {'succeeded' if result.success else 'failed'}")
        if result.errors:
            for e in result.errors:
                print(f"  Error: {e}")

    if not result.success:
        sys.exit(1)


def cmd_diagnostics(manager, args):
    diagnostics = manager.get_diagnostics()
    if args.get("--json"):
        print(json.dumps(diagnostics.to_dict(), indent=2, default=str))
    else:
        print("=== Diagnostics ===")
        print(f"Target: {diagnostics.target}")
        print(f"Runtime ID: {diagnostics.runtime_id}")
        print(f"State: {diagnostics.state}")
        print(f"Root: {diagnostics.root}")
        print(f"Free disk: {_fmt_bytes(diagnostics.free_disk_bytes)}")
        print(f"Locked: {diagnostics.locked}")
        if diagnostics.component_versions:
            print("Component versions:")
            for k, v in diagnostics.component_versions.items():
                print(f"  {k}: {v}")
        if diagnostics.validation_errors:
            print("Validation errors:")
            for e in diagnostics.validation_errors:
                print(f"  - {e}")


def cmd_env(manager, args):
    env = manager.get_environment()
    for k, v in sorted(env.items()):
        print(f"{k}={v}")


def cmd_remove(manager, args):
    if not args.get("--yes"):
        response = input("Remover o runtime Playwright? Esta operacao nao pode ser desfeita. [s/N] ")
        if response.lower() not in ("s", "sim", "y", "yes"):
            print("Operacao cancelada.")
            return
    manager.remove()
    print("Runtime removido.")


def _fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


COMMANDS = {
    "inspect": cmd_inspect,
    "install": cmd_install,
    "validate": cmd_validate,
    "repair": cmd_repair,
    "diagnostics": cmd_diagnostics,
    "env": cmd_env,
    "remove": cmd_remove,
}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Playwright runtime management CLI")
    parser.add_argument("command", choices=list(COMMANDS.keys()), help="Command to execute")
    parser.add_argument("--cache-dir", help="Cache directory override")
    parser.add_argument("--target", help="Target platform override")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--quick", action="store_true", help="Quick validation")
    parser.add_argument("--full", action="store_true", help="Full validation (with checksums)")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")

    parsed = parser.parse_args()
    args = vars(parsed)

    try:
        manager = get_manager(args)
    except Exception as e:
        print(f"Erro ao inicializar manager: {e}", file=sys.stderr)
        sys.exit(1)

    cmd_fn = COMMANDS[args["command"]]
    try:
        cmd_fn(manager, args)
    except Exception as e:
        print(f"Erro: {e}", file=sys.stderr)
        if args.get("--json"):
            print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
