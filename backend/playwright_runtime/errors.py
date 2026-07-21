"""Structured error hierarchy for Playwright runtime operations."""

import sys
from pathlib import Path


class PlaywrightRuntimeError(Exception):
    """Base error for all Playwright runtime operations."""

    def __init__(self, code, message, component=None, target=None, path=None, cause=None, suggestion=None):
        super().__init__(message)
        self.code = code
        self.component = component
        self.target = target
        self.path = str(path) if path else None
        self.cause = cause
        self.suggestion = suggestion

    def to_dict(self):
        d = {"code": self.code, "message": str(self)}
        for k in ("component", "target", "path", "suggestion"):
            v = getattr(self, k, None)
            if v is not None:
                d[k] = v
        return d


class UnsupportedTargetError(PlaywrightRuntimeError):
    def __init__(self, target, message=None, **kw):
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_UNSUPPORTED_TARGET",
            message=message or f"Runtime target nao suportado: {target}",
            target=target,
            suggestion="Verifique se ha spec versionada para esta plataforma",
            **kw,
        )


class SpecInvalidError(PlaywrightRuntimeError):
    def __init__(self, detail=None, **kw):
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_SPEC_INVALID",
            message=f"Especificacao de runtime invalida: {detail}" if detail else "Especificacao de runtime invalida",
            suggestion="Corrija o arquivo shared/playwright-runtime-targets.json",
            **kw,
        )


class LockedError(PlaywrightRuntimeError):
    def __init__(self, target, **kw):
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_LOCKED",
            message=f"Instalacao ja em andamento para {target}",
            target=target,
            suggestion="Aguarde a instalacao atual terminar ou remova o lock manualmente",
            **kw,
        )


class DiskSpaceInsufficientError(PlaywrightRuntimeError):
    def __init__(self, available, required, path_obj, **kw):
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_DISK_SPACE_INSUFFICIENT",
            message=f"Espaco em disco insuficiente: disponivel {_fmt_bytes(available)}, necessario {_fmt_bytes(required)} em {path_obj}",
            path=str(path_obj),
            suggestion="Libere espaco em disco ou escolha outro diretorio via PROSPECTOS_CACHE_DIR",
            **kw,
        )
        self.available = available
        self.required = required


class DownloadFailedError(PlaywrightRuntimeError):
    def __init__(self, url, status_code=None, extra_message=None, **kw):
        msg = f"Download falhou: {url}"
        if status_code:
            msg += f" (HTTP {status_code})"
        if extra_message:
            msg += f": {extra_message}"
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_DOWNLOAD_FAILED",
            message=msg,
            cause=f"HTTP {status_code}" if status_code else None,
            suggestion="Verifique sua conexao com a internet",
        )
        self.url = url
        self.status_code = status_code


class DownloadTimeoutError(PlaywrightRuntimeError):
    def __init__(self, url, timeout, **kw):
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_DOWNLOAD_TIMEOUT",
            message=f"Download excedeu o tempo limite de {timeout}s: {url}",
            suggestion="Tente novamente ou aumente o timeout",
            **kw,
        )
        self.url = url
        self.timeout = timeout


class ChecksumMismatchError(PlaywrightRuntimeError):
    def __init__(self, component, expected, actual, path_obj=None, **kw):
        msg = f"Checksum SHA-256 nao confere para {component}"
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_CHECKSUM_MISMATCH",
            message=msg,
            component=component,
            path=str(path_obj) if path_obj else None,
            suggestion="O arquivo pode estar corrompido. O download sera repetido.",
            **kw,
        )
        self.expected = expected
        self.actual = actual


class ArchiveInvalidError(PlaywrightRuntimeError):
    def __init__(self, path_obj, detail=None, **kw):
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_ARCHIVE_INVALID",
            message=f"Archive invalido: {path_obj}" + (f" ({detail})" if detail else ""),
            path=str(path_obj),
            suggestion="O archive pode estar corrompido ou ser invalido",
            **kw,
        )


class ExtractionFailedError(PlaywrightRuntimeError):
    def __init__(self, path_obj, detail=None, **kw):
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_EXTRACTION_FAILED",
            message=f"Falha na extracao: {path_obj}" + (f" ({detail})" if detail else ""),
            path=str(path_obj),
            suggestion="Tente baixar o arquivo novamente",
            **kw,
        )


class PathTraversalError(PlaywrightRuntimeError):
    def __init__(self, entry_path, **kw):
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_PATH_TRAVERSAL",
            message=f"Path traversal detectado no archive: {entry_path}",
            suggestion="O archive pode ser malicioso ou estar corrompido",
            **kw,
        )


class NodeInvalidError(PlaywrightRuntimeError):
    def __init__(self, detail=None, **kw):
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_NODE_INVALID",
            message=f"Node.js invalido: {detail}" if detail else "Node.js invalido",
            suggestion="Execute repair() para reinstalar o runtime",
            **kw,
        )


class DriverInvalidError(PlaywrightRuntimeError):
    def __init__(self, detail=None, **kw):
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_DRIVER_INVALID",
            message=f"Driver Playwright invalido: {detail}" if detail else "Driver Playwright invalido",
            suggestion="Execute repair() para reinstalar o runtime",
            **kw,
        )


class BrowserInstallFailedError(PlaywrightRuntimeError):
    def __init__(self, browser, exit_code=None, stderr=None, **kw):
        msg = f"Falha na instalacao do browser {browser}"
        if exit_code is not None:
            msg += f" (codigo {exit_code})"
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_BROWSER_INSTALL_FAILED",
            message=msg,
            component=browser,
            suggestion="Tente novamente ou execute repair()",
            **kw,
        )
        self.browser = browser
        self.exit_code = exit_code
        self.stderr = stderr


class BrowserInvalidError(PlaywrightRuntimeError):
    def __init__(self, browser, detail=None, **kw):
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_BROWSER_INVALID",
            message=f"Browser {browser} invalido: {detail}" if detail else f"Browser {browser} invalido",
            component=browser,
            suggestion="Execute repair() para reinstalar",
            **kw,
        )


class IncompleteInstallationError(PlaywrightRuntimeError):
    def __init__(self, target, missing_components=None, **kw):
        msg = f"Instalacao incompleta para {target}"
        if missing_components:
            msg += f": componentes ausentes: {', '.join(missing_components)}"
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_INCOMPLETE",
            message=msg,
            target=target,
            suggestion="Execute repair() para completar a instalacao",
            **kw,
        )
        self.missing_components = missing_components or []


class CorruptedInstallationError(PlaywrightRuntimeError):
    def __init__(self, target, detail=None, **kw):
        msg = f"Instalacao corrompida para {target}"
        if detail:
            msg += f": {detail}"
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_CORRUPTED",
            message=msg,
            target=target,
            suggestion="Execute repair() para reconstruir o runtime",
            **kw,
        )


class ValidationFailedError(PlaywrightRuntimeError):
    def __init__(self, errors=None, **kw):
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_VALIDATION_FAILED",
            message="Validacao do runtime falhou",
            suggestion="Execute repair() para corrigir",
            **kw,
        )
        self.validation_errors = errors or []


class CancelledError(PlaywrightRuntimeError):
    def __init__(self, stage=None, **kw):
        msg = "Operacao cancelada"
        if stage:
            msg += f" durante: {stage}"
        super().__init__(
            code="PLAYWRIGHT_RUNTIME_CANCELLED",
            message=msg,
            **kw,
        )


def _fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
