"""Tests for playwright_runtime.extractor module."""

import os
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright_runtime.extractor import safe_extract_tar, safe_extract_tgz
from playwright_runtime.errors import PathTraversalError, ArchiveInvalidError


def _make_tar(path, entries):
    """Create a tar file with given entries.

    entries: list of (name, data_or_None_for_dir, link_target_or_None)
    """
    with tarfile.open(str(path), "w") as tar:
        for entry in entries:
            name, data, link = entry
            if link:
                info = tarfile.TarInfo(name=name)
                info.type = tarfile.SYMTYPE
                info.linkname = link
                info.size = 0
                tar.addfile(info)
            elif data is None:
                info = tarfile.TarInfo(name=name)
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            else:
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))


import io


class TestSafeExtractTar:
    def test_normal_extraction(self, tmp_path):
        archive = tmp_path / "test.tar"
        _make_tar(archive, [
            ("file1.txt", b"hello", None),
            ("subdir/", None, None),
            ("subdir/file2.txt", b"world", None),
        ])

        dest = tmp_path / "out"
        safe_extract_tar(archive, dest)

        assert (dest / "file1.txt").exists()
        assert (dest / "subdir").is_dir()
        assert (dest / "subdir" / "file2.txt").exists()
        assert (dest / "file1.txt").read_bytes() == b"hello"

    def test_traversal_upward(self, tmp_path):
        archive = tmp_path / "traversal.tar"
        _make_tar(archive, [
            ("../../outside.txt", b"evil", None),
        ])

        dest = tmp_path / "out"
        with pytest.raises(PathTraversalError):
            safe_extract_tar(archive, dest)

    def test_absolute_path(self, tmp_path):
        archive = tmp_path / "abs.tar"
        _make_tar(archive, [
            ("/etc/passwd", b"evil", None),
        ])

        dest = tmp_path / "out"
        with pytest.raises(PathTraversalError):
            safe_extract_tar(archive, dest)

    def test_symlink_to_outside(self, tmp_path):
        archive = tmp_path / "symlink.tar"
        _make_tar(archive, [
            ("link", b"", "/etc/passwd"),
        ])

        dest = tmp_path / "out"
        with pytest.raises(PathTraversalError):
            safe_extract_tar(archive, dest)

    def test_symlink_with_traversal(self, tmp_path):
        archive = tmp_path / "symlink_traversal.tar"
        _make_tar(archive, [
            ("link", b"", "../outside"),
        ])

        dest = tmp_path / "out"
        with pytest.raises(PathTraversalError):
            safe_extract_tar(archive, dest)

    def test_invalid_archive(self, tmp_path):
        archive = tmp_path / "invalid.tar"
        archive.write_bytes(b"not a tar archive")

        dest = tmp_path / "out"
        with pytest.raises(ArchiveInvalidError):
            safe_extract_tar(archive, dest)

    def test_missing_archive(self, tmp_path):
        archive = tmp_path / "missing.tar"
        dest = tmp_path / "out"
        with pytest.raises(Exception):
            safe_extract_tar(archive, dest)

    def test_safe_symlink_within(self, tmp_path):
        archive = tmp_path / "safe_sym.tar"
        _make_tar(archive, [
            ("target.txt", b"hello", None),
            ("link.txt", b"", "target.txt"),
        ])

        dest = tmp_path / "out"
        safe_extract_tar(archive, dest)

        assert (dest / "target.txt").exists()
        assert (dest / "link.txt").exists()

    def test_extraction_interrupted(self, tmp_path):
        """Partial extraction should not leave files outside dest."""
        archive = tmp_path / "multi.tar"
        _make_tar(archive, [
            ("ok.txt", b"ok", None),
            ("../../bad.txt", b"evil", None),
        ])

        dest = tmp_path / "out"
        dest.mkdir()

        with pytest.raises(PathTraversalError):
            safe_extract_tar(archive, dest)

    def test_empty_archive(self, tmp_path):
        archive = tmp_path / "empty.tar"
        _make_tar(archive, [])

        dest = tmp_path / "out"
        safe_extract_tar(archive, dest)
        assert dest.exists()
        assert len(list(dest.iterdir())) == 0


class TestSafeExtractTgz:
    def test_tgz_extraction(self, tmp_path):
        import gzip
        archive = tmp_path / "test.tgz"
        with gzip.open(archive, "wb") as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                info = tarfile.TarInfo(name="hello.txt")
                info.size = 5
                tar.addfile(info, io.BytesIO(b"hello"))

        dest = tmp_path / "out"
        safe_extract_tgz(archive, dest)
        assert (dest / "hello.txt").exists()

    def test_tgz_traversal(self, tmp_path):
        import gzip
        archive = tmp_path / "bad.tgz"
        with gzip.open(archive, "wb") as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                info = tarfile.TarInfo(name="../../bad.txt")
                info.size = 3
                tar.addfile(info, io.BytesIO(b"bad"))

        dest = tmp_path / "out"
        with pytest.raises(PathTraversalError):
            safe_extract_tgz(archive, dest)
