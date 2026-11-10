"""Purga: la ÚNICA vía de borrado de originales de toda la aplicación (invariante 2).

- Un elemento se purga a los 30 días de entrar en la papelera, o antes si el propietario vacía la
  papelera con confirmación escrita.
- El original solo se borra del disco cuando ningún elemento de ningún espacio lo usa.
- La fila del original se conserva (con ``purged_at``): el contenedor de copias guarda su copia 30 días
  más y la verificación de integridad sabe que su ausencia es esperada.

Una prueba automática comprueba que ningún otro módulo borra ficheros de ``originals/``.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Asset, Blob
from app.services import audit
from app.storage.files import Storage

log = logging.getLogger(__name__)

TRASH_DAYS = 30


def purge_assets(
    db: Session, storage: Storage, assets: list[Asset], *, actor_id: uuid.UUID | None, reason: str
) -> int:
    """Borra de verdad estos elementos (ya en la papelera) y los originales que queden sin uso."""
    if not assets:
        return 0
    by_space: dict[uuid.UUID, int] = {}
    blob_ids = []
    for asset in assets:
        if asset.trashed_at is None:
            raise ValueError("Solo se purga lo que está en la papelera")
        by_space[asset.space_id] = by_space.get(asset.space_id, 0) + 1
        blob_ids.append(asset.blob_id)
        db.delete(asset)
    db.flush()
    now = datetime.now(UTC)
    for blob_id in blob_ids:
        db.execute(update(Blob).where(Blob.id == blob_id).values(ref_count=Blob.ref_count - 1))
    db.execute(
        update(Blob)
        .where(Blob.id.in_(blob_ids), Blob.ref_count <= 0, Blob.purged_at.is_(None))
        .values(purge_after=now)
    )
    for space_id, count in by_space.items():
        audit.record(
            db,
            "asset.purged",
            actor_id=actor_id,
            space_id=space_id,
            detail={"count": count, "reason": reason},
        )
    removed = purge_unreferenced_blobs(db, storage)
    log.info("Purga", extra={"assets": len(assets), "originals_removed": removed, "reason": reason})
    return len(assets)


def purge_unreferenced_blobs(db: Session, storage: Storage) -> int:
    blobs = list(
        db.scalars(
            select(Blob)
            .where(Blob.ref_count <= 0, Blob.purged_at.is_(None), Blob.purge_after <= datetime.now(UTC))
            .with_for_update(skip_locked=True)
        )
    )
    for blob in blobs:
        # Comprobación final dentro de la transacción: nadie ha vuelto a usar el original.
        if db.scalar(select(Asset.id).where(Asset.blob_id == blob.id).limit(1)) is not None:
            blob.purge_after = None
            continue
        storage.original_path(blob.sha256, blob.ext).unlink(missing_ok=True)
        shutil.rmtree(storage.derivative_dir(blob.sha256), ignore_errors=True)
        blob.purged_at = datetime.now(UTC)
        blob.ref_count = 0
    return len(blobs)


def purge_expired_trash(
    db: Session, storage: Storage, *, days: int = TRASH_DAYS, now: datetime | None = None
) -> int:
    limit = (now or datetime.now(UTC)) - timedelta(days=days)
    assets = list(
        db.scalars(select(Asset).where(Asset.trashed_at.is_not(None), Asset.trashed_at <= limit).limit(5000))
    )
    return purge_assets(db, storage, assets, actor_id=None, reason="caducada")
