"""Secure HTTP download with streaming, retries, checksum validation, and atomic rename."""

import hashlib
import logging
import os
import time
from pathlib import Path

from .errors import (
    DownloadFailedError,
    ChecksumMismatchError,
    CancelledError,
)

logger = logging.getLogger(__name__)

DEFAULT_CONNECT_TIMEOUT = 15
DEFAULT_READ_TIMEOUT = 60
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF = 1.0

USER_AGENT = "ProspectOS/1.0 PlaywrightRuntimeManager"


class DownloadResult:
    def __init__(self, path: Path, sha256: str, size: int, cached: bool = False):
        self.path = path
        self.sha256 = sha256
        self.size = size
        self.cached = cached


class Downloader:
    """Downloads files with streaming, retries, checksum validation, and caching."""

    def __init__(self, cache_dir: Path, http_client=None):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._http = http_client or _DefaultHttpClient()

    def download(
        self,
        url: str,
        expected_sha256: str,
        archive_name: str = "",
        progress=None,
        cancel=None,
        max_retries=DEFAULT_MAX_RETRIES,
        connect_timeout=DEFAULT_CONNECT_TIMEOUT,
        read_timeout=DEFAULT_READ_TIMEOUT,
    ) -> DownloadResult:
        name = archive_name or url.rsplit("/", 1)[-1] or "download"
        cache_name = f"{expected_sha256}-{name}"
        cached_path = self.cache_dir / cache_name

        if cached_path.exists():
            actual_hash = _hash_file(cached_path)
            if actual_hash == expected_sha256:
                logger.info("Reutilizando download em cache: %s", cached_path)
                return DownloadResult(path=cached_path, sha256=expected_sha256, size=cached_path.stat().st_size, cached=True)
            logger.warning("Cache corrompido para %s, baixando novamente", name)
            cached_path.unlink(missing_ok=True)

        partial_path = cached_path.with_suffix(".partial")
        last_error = None

        for attempt in range(1, max_retries + 1):
            if cancel and cancel():
                partial_path.unlink(missing_ok=True)
                raise CancelledError(stage="download")

            try:
                if progress:
                    progress(stage="downloading", component=name, percent=0)

                actual_hash, size = self._http.download(url, partial_path, progress, cancel, connect_timeout, read_timeout)

                if cancel and cancel():
                    partial_path.unlink(missing_ok=True)
                    raise CancelledError(stage="download")

                if actual_hash != expected_sha256:
                    partial_path.unlink(missing_ok=True)
                    raise ChecksumMismatchError(component=name, expected=expected_sha256, actual=actual_hash)

                os.rename(str(partial_path), str(cached_path))
                logger.info("Download concluido: %s (%d bytes)", name, size)
                return DownloadResult(path=cached_path, sha256=expected_sha256, size=size)

            except ChecksumMismatchError:
                raise
            except Exception as e:
                last_error = e
                partial_path.unlink(missing_ok=True)
                if attempt < max_retries:
                    backoff = DEFAULT_BACKOFF * (2 ** (attempt - 1))
                    logger.warning("Download falhou (tentativa %d/%d): %s. Tentando novamente em %.1fs", attempt, max_retries, e, backoff)
                    time.sleep(backoff)
                else:
                    logger.error("Download falhou apos %d tentativas: %s", max_retries, e)

        if isinstance(last_error, ChecksumMismatchError):
            raise last_error
        raise DownloadFailedError(url=url) from last_error


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class _DefaultHttpClient:
    """Minimal HTTP client using urllib."""

    def download(self, url, dest, progress, cancel, connect_timeout, read_timeout):
        import urllib.request
        import urllib.error

        if not url.startswith("https://"):
            raise DownloadFailedError(url=url, extra_message=f"URL nao HTTPS rejeitada: {url}")

        h = hashlib.sha256()
        total_size = 0
        downloaded = 0

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

        try:
            with urllib.request.urlopen(req, timeout=connect_timeout) as response:
                if response.status != 200:
                    raise DownloadFailedError(url=url, status_code=response.status)

                content_length = response.headers.get("Content-Length")
                if content_length:
                    total_size = int(content_length)

                with open(dest, "wb") as f:
                    while True:
                        if cancel and cancel():
                            break
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        h.update(chunk)
                        downloaded += len(chunk)
                        if progress and total_size:
                            pct = min(100.0, downloaded / total_size * 100)
                            progress(stage="downloading", component=dest.name, completed_bytes=downloaded, total_bytes=total_size, percent=pct)
        except urllib.error.HTTPError as e:
            raise DownloadFailedError(url=url, status_code=e.code) from e
        except urllib.error.URLError as e:
            raise DownloadFailedError(url=url, extra_message=str(e.reason)) from e

        return h.hexdigest(), downloaded
