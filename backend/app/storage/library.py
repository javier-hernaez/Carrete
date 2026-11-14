"""Biblioteca en disco: «que se guarden todas las fotos en el mini PC» en carpetas normales.

``datos/library/<Espacio>/<Álbum>/AAAA-MM-DD_HHMMSS_nombre.ext`` y ``<Espacio>/Sin álbum/AAAA/MM/…``,
hechos con **enlaces duros** a los originales: no ocupa espacio y se abre con cualquier explorador de
archivos aunque Carrete no esté funcionando. Es de solo lectura y se reconstruye entera a partir de la
base de datos (nunca es la fuente de verdad): se construye en ``library.nuevo`` y se cambia de golpe.

Incluye lo que vale y lo que está sin revisar; no lo descartado ni lo que está en la papelera.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Album, AlbumAsset, Asset, Blob, Space
from app.storage.files import Storage
from app.storage.naming import UniqueNames, file_name, folders_for, safe_component

log = logging.getLogger(__name__)

README = """Biblioteca de Carrete
=====================

Estas carpetas son una vista de las fotos guardadas en Carrete, ordenadas por espacio y álbum.
Son enlaces a los originales: no ocupan espacio extra y se pueden abrir y copiar sin Carrete.

- No guardes aquí nada tuyo: la carpeta se vuelve a generar cada noche.
- Borrar algo aquí no borra la foto de Carrete.
"""


@dataclass
class LibraryResult:
    spaces: int
    files: int
    missing: int


def build(db: Session, storage: Storage) -> LibraryResult:
    target = storage.library
    staging = storage.root / "library.nuevo"
    old = storage.root / "library.anterior"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    (staging / "LEEME.txt").write_text(README, encoding="utf-8")

    files = missing = 0
    space_names = UniqueNames()
    spaces = list(db.scalars(select(Space).where(Space.archived_at.is_(None)).order_by(Space.name)))
    for space in spaces:
        root = space_names.claim("", safe_component(space.name, "Espacio"))
        albums: dict[object, list[str]] = {}
        rows = db.execute(
            select(AlbumAsset.asset_id, Album.name)
            .join(Album, Album.id == AlbumAsset.album_id)
            .where(Album.space_id == space.id)
        )
        for asset_id, name in rows:
            albums.setdefault(asset_id, []).append(name)
        names = UniqueNames()
        items = db.execute(
            select(Asset, Blob)
            .join(Blob, Blob.id == Asset.blob_id)
            .where(Asset.space_id == space.id, Asset.trashed_at.is_(None), Asset.review_state != "discarded")
            .order_by(Asset.taken_at_local, Asset.id)
        ).tuples()
        for asset, blob in items:
            source = storage.original_path(blob.sha256, blob.ext)
            if not source.exists():
                missing += 1
                continue
            name = file_name(asset.original_filename, asset.taken_at_local, blob.ext, normalized=True)
            for folder in folders_for("album", asset.taken_at_local, sorted(albums.get(asset.id, []))):
                relative = names.claim(folder, name)
                dest = staging / root / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.link(source, dest)
                files += 1

    # Cambio de golpe: quien mire la carpeta nunca ve una biblioteca a medias.
    shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        target.rename(old)
    staging.rename(target)
    shutil.rmtree(old, ignore_errors=True)
    log.info(
        "Biblioteca en disco reconstruida", extra={"spaces": len(spaces), "files": files, "missing": missing}
    )
    return LibraryResult(len(spaces), files, missing)
