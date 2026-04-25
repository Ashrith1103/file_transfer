"""SHA-256 checksum helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    """Return the hex-encoded SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    """Return the hex-encoded SHA-256 digest of the file at *path*.

    Reads the file in *block_size* chunks so that arbitrarily large files can
    be hashed without loading them entirely into memory.
    """
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()
