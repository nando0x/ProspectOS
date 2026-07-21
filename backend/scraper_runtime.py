"""Bridge between jobs.py and the PlaywrightRuntimeManager — resolves the scraper
binary, ensures the Playwright runtime is ready, and provides the controlled
environment for the scraper subprocess."""

import logging
import os
from pathlib import Path

import runtime_targets
from playwright_runtime import PlaywrightRuntimeManager, RuntimeState
from playwright_runtime.errors import (
    PlaywrightRuntimeError,
    UnsupportedTargetError,
    LockedError,
    DiskSpaceInsufficientError,
    CancelledError,
    DownloadFailedError,
    ChecksumMismatchError,
)

logger = logging.getLogger(__name__)

RUNTIME_PROGRESS_MESSAGES = {
    "checking": "Preparando mecanismo de busca...",
    "downloading_playwright_core": "Baixando componentes do navegador...",
    "downloading_node": "Baixando componentes do navegador...",
    "verifying_downloads": "Verificando componentes baixados...",
    "extracting_playwright_core": "Instalando componentes do navegador...",
    "extracting_node": "Instalando componentes do navegador...",
    "assembling_driver": "Montando ambiente de busca...",
    "validating_driver": "Validando ambiente de busca...",
    "installing_browser": "Instalando navegador...",
    "validating_browser": "Validando navegador...",
    "publishing": "Finalizando ambiente de busca...",
    "ready": "Ambiente de busca pronto.",
}

RUNTIME_ERROR_MESSAGES = {
    "DISK_SPACE_INSUFFICIENT": "Espaço insuficiente para preparar o navegador.",
    "DOWNLOAD_FAILED": "Não foi possível baixar os componentes de busca.",
    "CHECKSUM_MISMATCH": "A verificação dos componentes falhou.",
    "UNSUPPORTED_TARGET": "Este sistema ainda não é compatível com a busca do Google Maps.",
    "LOCKED": "O ambiente de busca está sendo preparado por outro processo.",
    "CANCELLED": "Preparação cancelada.",
    "CORRUPTED_REPAIR_FAILED": "Não foi possível reparar o ambiente de busca.",
}


class ScraperRuntimeError(RuntimeError):
    def __init__(self, message: str, code: str = "", detail: str = ""):
        super().__init__(message)
        self.code = code
        self.detail = detail


def user_message_for_runtime_error(exc: Exception) -> str:
    if isinstance(exc, DiskSpaceInsufficientError):
        return RUNTIME_ERROR_MESSAGES["DISK_SPACE_INSUFFICIENT"]
    if isinstance(exc, DownloadFailedError):
        return RUNTIME_ERROR_MESSAGES["DOWNLOAD_FAILED"]
    if isinstance(exc, ChecksumMismatchError):
        return RUNTIME_ERROR_MESSAGES["CHECKSUM_MISMATCH"]
    if isinstance(exc, UnsupportedTargetError):
        return RUNTIME_ERROR_MESSAGES["UNSUPPORTED_TARGET"]
    if isinstance(exc, LockedError):
        return RUNTIME_ERROR_MESSAGES["LOCKED"]
    if isinstance(exc, CancelledError):
        return RUNTIME_ERROR_MESSAGES["CANCELLED"]
    if isinstance(exc, PlaywrightRuntimeError):
        code = getattr(exc, "code", "")
        if "CORRUPTED" in code or "INCOMPLETE" in code:
            return RUNTIME_ERROR_MESSAGES["CORRUPTED_REPAIR_FAILED"]
    return "Erro ao preparar ambiente de busca."


def runtime_progress_callback(event_dict: dict):
    stage = event_dict.get("stage", "")
    message = RUNTIME_PROGRESS_MESSAGES.get(stage, "Preparando ambiente de busca...")
    logger.info("[runtime] %s (stage=%s)", message, stage)


def resolve_and_prepare_runtime(
    progress=None,
    cancel=None,
) -> tuple[Path, dict[str, str]]:
    """Resolve the scraper path and prepare the Playwright runtime.

    Returns (scraper_path, runtime_environment).

    On unsupported targets, returns the scraper path and an empty env dict
    so the caller can fall back to the legacy flow.
    """
    target = runtime_targets.current_target()
    logger.info("target=%s", target)

    scraper_path = runtime_targets.resolve_scraper()
    runtime_targets.validate_executable(scraper_path, "Scraper do Google Maps")

    if target != "darwin-arm64":
        logger.info(
            "target=%s nao usa runtime gerenciado, retornando ambiente vazio",
            target,
        )
        return scraper_path, {}

    manager = PlaywrightRuntimeManager()

    try:
        installation = manager.ensure_ready(
            progress=progress or runtime_progress_callback,
            cancel=cancel,
        )
        logger.info(
            "runtime pronto target=%s runtime_id=%s path=%s",
            installation.target, installation.runtime_id, installation.path,
        )
    except (PlaywrightRuntimeError, UnsupportedTargetError, LockedError,
            DiskSpaceInsufficientError, CancelledError, DownloadFailedError,
            ChecksumMismatchError) as exc:
        msg = user_message_for_runtime_error(exc)
        logger.error("runtime falhou: %s | detalhe: %s", msg, exc)
        raise ScraperRuntimeError(message=msg, code=type(exc).__name__, detail=str(exc)) from exc

    runtime_env = manager.get_environment()

    _validate_env_paths(runtime_env)

    env = {
        **os.environ,
        **runtime_env,
    }

    return scraper_path, env


def _validate_env_paths(env: dict[str, str]):
    for key in ("PLAYWRIGHT_DRIVER_PATH", "PLAYWRIGHT_BROWSERS_PATH"):
        value = env.get(key, "")
        if not value:
            raise ScraperRuntimeError(
                message=f"Variavel {key} vazia no runtime.",
                code="EMPTY_ENV_VAR",
            )
        p = Path(value)
        if not p.is_absolute():
            raise ScraperRuntimeError(
                message=f"{key} nao e absoluto: {value}",
                code="NON_ABSOLUTE_PATH",
            )
        if not p.exists():
            raise ScraperRuntimeError(
                message=f"{key} nao existe: {value}",
                code="MISSING_PATH",
            )
