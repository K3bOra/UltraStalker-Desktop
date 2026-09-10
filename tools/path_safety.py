from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Iterator


def is_linklike(path: Path) -> bool:
    """Return True for symlinks, Windows junctions and other reparse points."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction and is_junction():
            return True
        if os.name == "nt":
            attrs = getattr(path.lstat(), "st_file_attributes", 0)
            if attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                return True
        return False
    except OSError:
        # An unreadable path cannot be proven to be a regular payload object.
        return True


def walk_payload(root: Path) -> Iterator[Path]:
    """Walk a release tree without ever descending into link-like directories.

    ``Path.rglob`` can make traversal behavior dependent on Python/filesystem
    details.  Release verification should reject a junction/symlink itself while
    never enumerating its target, which may live outside the payload root.
    """
    root = Path(root).resolve()

    def raise_error(exc: OSError) -> None:
        raise exc

    for current, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=False, onerror=raise_error
    ):
        base = Path(current)
        kept_dirs: list[str] = []
        for name in sorted(dirnames):
            path = base / name
            yield path
            if not is_linklike(path):
                kept_dirs.append(name)
        # Prune before os.walk can descend into a symlink/junction/reparse dir.
        dirnames[:] = kept_dirs
        for name in sorted(filenames):
            yield base / name
