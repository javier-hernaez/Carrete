"""Papelera: eliminar manda a la papelera; 30 días para recuperar."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import Asset, User
from app.services import audit
from app.services.audit import RequestInfo
from app.services.errors import Invalid
from app.services.spaces import SpaceAccess
from app.storage.files import Storage
from app.storage.purge import purge_assets


def _ids_in_space(db: Session, space_id: uuid.UUID, ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Solo los identificadores que son de este espacio: los ajenos se ignoran sin revelar nada."""
    return list(db.scalars(select(Asset.id).where(Asset.space_id == space_id, Asset.id.in_(ids))))


def move_to_trash(
    db: Session, acc: SpaceAccess, user: User, ids: list[uuid.UUID], request: RequestInfo
) -> int:
    valid = _ids_in_space(db, acc.space.id, ids)
    result = db.execute(
        update(Asset)
        .where(Asset.id.in_(valid), Asset.trashed_at.is_(None))
        .values(trashed_at=datetime.now(UTC), trashed_by=user.id)
    )
    count = int(result.rowcount)  # type: ignore[attr-defined]
    if count:
        audit.record(
            db,
            "asset.trashed",
            actor_id=user.id,
            space_id=acc.space.id,
            request=request,
            detail={"count": count, "ids": [str(i) for i in valid[:50]]},
        )
    return count


def restore(db: Session, acc: SpaceAccess, user: User, ids: list[uuid.UUID], request: RequestInfo) -> int:
    """El propietario recupera cualquier cosa; un colaborador solo deshace lo que él mismo eliminó."""
    valid = _ids_in_space(db, acc.space.id, ids)
    stmt = update(Asset).where(Asset.id.in_(valid), Asset.trashed_at.is_not(None))
    if not acc.can("owner"):
        stmt = stmt.where(Asset.trashed_by == user.id)
    result = db.execute(stmt.values(trashed_at=None, trashed_by=None))
    count = int(result.rowcount)  # type: ignore[attr-defined]
    if count:
        audit.record(
            db,
            "asset.restored",
            actor_id=user.id,
            space_id=acc.space.id,
            request=request,
            detail={"count": count},
        )
    return count


def trash_count(db: Session, space_id: uuid.UUID) -> int:
    return int(
        db.scalar(select(func.count()).where(Asset.space_id == space_id, Asset.trashed_at.is_not(None))) or 0
    )


def empty(
    db: Session, storage: Storage, acc: SpaceAccess, user: User, confirm_name: str, request: RequestInfo
) -> int:
    """Vaciar ya: solo el propietario, tecleando el nombre del espacio. Queda en la auditoría."""
    if confirm_name.strip() != acc.space.name:
        raise Invalid("Escribe el nombre del espacio exactamente para confirmar", code="confirm_mismatch")
    assets = list(
        db.scalars(select(Asset).where(Asset.space_id == acc.space.id, Asset.trashed_at.is_not(None)))
    )
    audit.record(
        db,
        "trash.emptied",
        actor_id=user.id,
        space_id=acc.space.id,
        request=request,
        detail={"count": len(assets)},
    )
    return purge_assets(db, storage, assets, actor_id=user.id, reason="vaciada")
