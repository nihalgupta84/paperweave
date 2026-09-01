"""Centralized hashing utilities for file and data identity."""

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 hex digest of a file, reading in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute the SHA-256 hex digest of a bytes object."""
    return hashlib.sha256(data).hexdigest()
