"""Tests for playwright_runtime.downloader module."""

import hashlib
import os
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright_runtime.downloader import Downloader, _hash_file
from playwright_runtime.errors import (
    PlaywrightRuntimeError,
    DownloadFailedError,
    ChecksumMismatchError,
    CancelledError,
)


class FakeHttpClient:
    def __init__(self, data=b"fake-content", status=200, fail_count=0):
        self.data = data
        self.status = status
        self.fail_count = fail_count
        self.call_count = 0

    def download(self, url, dest, progress, cancel, connect_timeout, read_timeout):
        if not url.startswith("https://"):
            raise DownloadFailedError(url=url, extra_message="URL nao HTTPS")

        self.call_count += 1

        if self.status != 200:
            raise DownloadFailedError(url=url, status_code=self.status)

        if self.call_count <= self.fail_count:
            raise IOError("Simulated network failure")

        if cancel and cancel():
            raise CancelledError(stage="download")

        h = hashlib.sha256()
        h.update(self.data)
        with open(dest, "wb") as f:
            f.write(self.data)

        return h.hexdigest(), len(self.data)


class TestDownloader:
    def test_successful_download(self, tmp_path):
        data = b"test-data"
        client = FakeHttpClient(data=data)
        downloader = Downloader(tmp_path, http_client=client)

        expected_hash = hashlib.sha256(data).hexdigest()
        result = downloader.download(
            url="https://example.com/file.tgz",
            expected_sha256=expected_hash,
            archive_name="file.tgz",
        )

        assert result.sha256 == expected_hash
        assert result.size == len(data)
        assert result.path.exists()
        assert result.cached is False

    def test_download_cached(self, tmp_path):
        data = b"cached-data"
        expected_hash = hashlib.sha256(data).hexdigest()
        cache_name = f"{expected_hash}-file.tgz"
        cached_path = tmp_path / cache_name
        cached_path.write_bytes(data)

        client = FakeHttpClient(data=data)
        downloader = Downloader(tmp_path, http_client=client)

        result = downloader.download(
            url="https://example.com/file.tgz",
            expected_sha256=expected_hash,
            archive_name="file.tgz",
        )

        assert result.cached is True
        assert client.call_count == 0

    def test_cache_corrupted_redownloads(self, tmp_path):
        data = b"real-data"
        expected_hash = hashlib.sha256(data).hexdigest()
        cache_name = f"{expected_hash}-file.tgz"
        cached_path = tmp_path / cache_name
        cached_path.write_bytes(b"corrupted-data")

        client = FakeHttpClient(data=data)
        downloader = Downloader(tmp_path, http_client=client)

        result = downloader.download(
            url="https://example.com/file.tgz",
            expected_sha256=expected_hash,
            archive_name="file.tgz",
        )

        assert result.cached is False
        assert client.call_count == 1
        assert result.sha256 == expected_hash

    def test_checksum_mismatch_raises(self, tmp_path):
        client = FakeHttpClient(data=b"real-data")
        downloader = Downloader(tmp_path, http_client=client)

        with pytest.raises(ChecksumMismatchError):
            downloader.download(
                url="https://example.com/file.tgz",
                expected_sha256="0" * 64,
                archive_name="file.tgz",
            )

    def test_http_404(self, tmp_path):
        client = FakeHttpClient(data=b"x", status=404)
        downloader = Downloader(tmp_path, http_client=client)

        with pytest.raises(DownloadFailedError):
            downloader.download(
                url="https://example.com/file.tgz",
                expected_sha256="0" * 64,
                archive_name="file.tgz",
                max_retries=1,
            )

    def test_http_url_rejected(self, tmp_path):
        client = FakeHttpClient()
        downloader = Downloader(tmp_path, http_client=client)

        with pytest.raises(PlaywrightRuntimeError):
            downloader.download(
                url="http://example.com/file.tgz",
                expected_sha256="0" * 64,
                archive_name="file.tgz",
                max_retries=1,
            )

    def test_cancellation_during_download(self, tmp_path):
        def cancel():
            return True

        client = FakeHttpClient(data=b"some-data")
        downloader = Downloader(tmp_path, http_client=client)

        with pytest.raises(CancelledError):
            downloader.download(
                url="https://example.com/file.tgz",
                expected_sha256="0" * 64,
                archive_name="file.tgz",
                cancel=cancel,
            )

    def test_partial_file_removed_on_error(self, tmp_path):
        client = FakeHttpClient(data=b"real-data")
        downloader = Downloader(tmp_path, http_client=client)

        expected_hash = hashlib.sha256(b"different-data").hexdigest()

        with pytest.raises(ChecksumMismatchError):
            downloader.download(
                url="https://example.com/file.tgz",
                expected_sha256=expected_hash,
                archive_name="file.tgz",
            )

        partials = list(tmp_path.glob("*.partial"))
        assert len(partials) == 0

    def test_retry_on_failure(self, tmp_path):
        data = b"retry-data"
        client = FakeHttpClient(data=data, fail_count=1)
        downloader = Downloader(tmp_path, http_client=client)

        expected_hash = hashlib.sha256(data).hexdigest()
        result = downloader.download(
            url="https://example.com/file.tgz",
            expected_sha256=expected_hash,
            archive_name="file.tgz",
            max_retries=3,
        )

        assert result.sha256 == expected_hash
        assert client.call_count == 2

    def test_max_retries_exceeded(self, tmp_path):
        """Fails after retries because checksum never matches."""
        client = FakeHttpClient(data=b"fail-data", fail_count=99)
        downloader = Downloader(tmp_path, http_client=client)

        expected_hash = hashlib.sha256(b"expected-hash").hexdigest()

        with pytest.raises(DownloadFailedError):
            downloader.download(
                url="https://example.com/file.tgz",
                expected_sha256=expected_hash,
                archive_name="file.tgz",
                max_retries=2,
            )

    def test_deterministic_cache_name(self, tmp_path):
        data = b"deterministic"
        expected_hash = hashlib.sha256(data).hexdigest()
        client = FakeHttpClient(data=data)
        downloader = Downloader(tmp_path, http_client=client)

        result = downloader.download(
            url="https://example.com/file.tgz",
            expected_sha256=expected_hash,
            archive_name="important.tgz",
        )

        expected_name = f"{expected_hash}-important.tgz"
        assert result.path.name == expected_name

    def test_progress_callback(self, tmp_path):
        data = b"x" * 65536 * 2
        client = FakeHttpClient(data=data)
        downloader = Downloader(tmp_path, http_client=client)

        events = []

        def progress(**kw):
            events.append(kw)

        expected_hash = hashlib.sha256(data).hexdigest()
        downloader.download(
            url="https://example.com/file.tgz",
            expected_sha256=expected_hash,
            archive_name="file.tgz",
            progress=progress,
        )

        assert len(events) > 0


class TestHashFile:
    def test_hash_file(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert _hash_file(f) == expected

    def test_hash_large_file(self, tmp_path):
        f = tmp_path / "large.bin"
        data = b"x" * 200000
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert _hash_file(f) == expected
