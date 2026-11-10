"""Almacenamiento en disco.

- ``originals/ab/cd/<sha256>.<ext>``: originales. Se escriben **una sola vez** por renombrado atómico de
  un fichero ya verificado y quedan en solo lectura (0444). Ningún código abre un original para
  escribir; la única vía de borrado es la purga.
- ``derivatives/<sha256>/``: miniaturas y vistas previas. Se pueden borrar y regenerar siempre.
- ``uploads/``: subidas a medias. ``exports/`` y ``library/``: exportaciones y biblioteca en disco.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

CHUNK = 1024 * 1024


class Storage:
    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def originals(self) -> Path:
        return self.root / "originals"

    @property
    def derivatives(self) -> Path:
        return self.root / "derivatives"

    @property
    def uploads(self) -> Path:
        return self.root / "uploads"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def library(self) -> Path:
        return self.root / "library"

    def original_path(self, sha256: str, ext: str) -> Path:
        _check_sha(sha256)
        return self.originals / sha256[:2] / sha256[2:4] / f"{sha256}.{ext}"

    def derivative_dir(self, sha256: str) -> Path:
        _check_sha(sha256)
        return self.derivatives / sha256

    def upload_path(self, upload_id: object) -> Path:
        return self.uploads / f"{upload_id}.part"

    def free_bytes(self) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(self.root).free

    def commit_original(self, temp: Path, sha256: str, ext: str) -> Path:
        """Convierte un fichero temporal ya verificado en original. Idempotente si ya existía."""
        dest = self.original_path(sha256, ext)
        if dest.exists():
            temp.unlink(missing_ok=True)
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        _fsync_file(temp)
        temp.chmod(0o444)
        temp.replace(dest)  # atómico dentro del mismo sistema de ficheros
        _fsync_dir(dest.parent)
        return dest


def _check_sha(value: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("SHA-256 no válido")


def _fsync_file(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
