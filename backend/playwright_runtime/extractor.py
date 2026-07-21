"""Safe archive extraction with path traversal protection."""

import logging
import tarfile
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def safe_extract_tar(archive_path: Path, dest_dir: Path, members=None):
    """Extract a tar archive safely, blocking path traversal and absolute paths."""
    dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    if not archive_path.exists():
        from .errors import ExtractionFailedError
        raise ExtractionFailedError(path_obj=archive_path, detail="Arquivo nao encontrado")

    try:
        with tarfile.open(str(archive_path), "r:*") as tar:
            if members is None:
                members = tar.getmembers()

            for member in members:
                _validate_member(member, dest_dir)

            tar.extractall(path=str(dest_dir), members=members, filter="data")
    except tarfile.ReadError as e:
        from .errors import ArchiveInvalidError
        raise ArchiveInvalidError(path_obj=archive_path, detail=str(e))
    except (OSError, IOError) as e:
        from .errors import ExtractionFailedError
        raise ExtractionFailedError(path_obj=archive_path, detail=str(e))


def safe_extract_tgz(archive_path: Path, dest_dir: Path):
    """Extract a .tgz (.tar.gz) archive safely."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_extract_tar(archive_path, dest_dir)


def _validate_member(member, dest_dir: Path):
    """Validate a tar member for safety."""
    name = member.name

    if not name or name.startswith("/"):
        raise _traversal_error(name)
    if ".." in name.split("/"):
        raise _traversal_error(name)
    if os.path.isabs(name):
        raise _traversal_error(name)

    if member.issym() or member.islnk():
        link_target = member.linkname
        if link_target:
            if link_target.startswith("/"):
                raise _traversal_error(name, f"symlink para path absoluto: {link_target}")

            resolved = (dest_dir / name).resolve().parent / link_target
            try:
                resolved = resolved.resolve()
            except (OSError, RuntimeError):
                raise _traversal_error(name, f"symlink nao resolve: {link_target}")

            try:
                resolved.relative_to(dest_dir.resolve())
            except ValueError:
                raise _traversal_error(name, f"symlink aponta para fora: {link_target}")


def _traversal_error(name, detail=None):
    from .errors import PathTraversalError
    msg = f"Path traversal detectado: {name}"
    if detail:
        msg += f" ({detail})"
    raise PathTraversalError(entry_path=name)
