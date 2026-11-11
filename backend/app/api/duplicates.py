"""Rutas de repetidas y actividad del espacio."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.assets import AssetOut, asset_out
from app.api.deps import DB, FullAuth, ReqInfo
from app.db.models import AuditEntry, User
from app.services import duplicates, spaces

router = APIRouter(prefix="/api/v1", tags=["repetidas"])


class DuplicateMemberOut(AssetOut):
    size_bytes: int
    original_filename: str
    has_exif_date: bool
    best: bool


class GroupOut(BaseModel):
    id: uuid.UUID
    distance: int
    members: list[DuplicateMemberOut]


def _group_out(group: Any, found: list[duplicates.Member]) -> GroupOut:
    return GroupOut(
        id=group.id,
        distance=group.distance,
        members=[
            DuplicateMemberOut(
                **asset_out(m.asset).model_dump(),
                size_bytes=m.blob.size_bytes,
                original_filename=m.asset.original_filename,
                has_exif_date=m.asset.taken_at_source == "exif",
                best=i == 0,
            )
            for i, m in enumerate(found)
        ],
    )


@router.get("/spaces/{space_id}/duplicates", response_model=list[GroupOut])
def list_groups(space_id: uuid.UUID, current: FullAuth, db: DB) -> list[GroupOut]:
    spaces.access(db, current.user, space_id)
    groups = duplicates.pending_groups(db, space_id)
    db.commit()  # cierra los grupos que se quedaron con un solo miembro
    return [_group_out(g, m) for g, m in groups]


class ResolveIn(BaseModel):
    keep: list[uuid.UUID] = Field(min_length=1, max_length=100)


class ResolveOut(BaseModel):
    trashed: list[uuid.UUID]


@router.post("/spaces/{space_id}/duplicates/{group_id}/resolve", response_model=ResolveOut)
def resolve(
    space_id: uuid.UUID, group_id: uuid.UUID, body: ResolveIn, current: FullAuth, db: DB, info: ReqInfo
) -> ResolveOut:
    acc = spaces.access(db, current.user, space_id, "collaborator")
    trashed = duplicates.resolve(
        db, acc, current.user, duplicates.get_group(db, space_id, group_id), body.keep, info
    )
    db.commit()
    return ResolveOut(trashed=trashed)


@router.post("/spaces/{space_id}/duplicates/{group_id}/reopen", status_code=204)
def reopen(space_id: uuid.UUID, group_id: uuid.UUID, current: FullAuth, db: DB) -> None:
    """Deshacer una resolución: vuelve a proponer el grupo (las fotos se recuperan aparte)."""
    spaces.access(db, current.user, space_id, "collaborator")
    duplicates.reopen(db, duplicates.get_group(db, space_id, group_id))
    db.commit()


@router.post("/spaces/{space_id}/duplicates/{group_id}/dismiss", status_code=204)
def dismiss(space_id: uuid.UUID, group_id: uuid.UUID, current: FullAuth, db: DB, info: ReqInfo) -> None:
    acc = spaces.access(db, current.user, space_id, "collaborator")
    duplicates.dismiss(db, acc, current.user, duplicates.get_group(db, space_id, group_id), info)
    db.commit()


class ObviousOut(BaseModel):
    groups: int
    keep: int
    trash: int
    trashed: list[uuid.UUID] = []
    group_ids: list[uuid.UUID] = []


@router.post("/spaces/{space_id}/duplicates/resolve-obvious", response_model=ObviousOut)
def resolve_obvious(
    space_id: uuid.UUID, current: FullAuth, db: DB, info: ReqInfo, apply: bool = False
) -> ObviousOut:
    """Resolver de una vez los grupos evidentes. Sin ``apply`` solo devuelve el resumen previo."""
    acc = spaces.access(db, current.user, space_id, "collaborator")
    found = duplicates.obvious(db, space_id)
    summary = ObviousOut(groups=len(found), keep=len(found), trash=sum(len(rest) for _, _, rest in found))
    if not apply:
        return summary
    for group, best, _ in found:
        summary.trashed += duplicates.resolve(db, acc, current.user, group, [best.asset.id], info)
        summary.group_ids.append(group.id)
    db.commit()
    return summary


# --- Actividad -----------------------------------------------------------------------------------------

ACTIVITY_ACTIONS = (
    "asset.uploaded",
    "asset.trashed",
    "asset.restored",
    "asset.purged",
    "asset.date_changed",
    "album.created",
    "album.renamed",
    "album.deleted",
    "album.assets_added",
    "duplicates.resolved",
    "trash.emptied",
    "invitation.accepted",
    "space.created",
    "space.renamed",
    "space.member_removed",
    "export.created",
)


class ActivityOut(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    actor: str | None
    action: str
    detail: dict[str, Any]


@router.get("/spaces/{space_id}/activity", response_model=list[ActivityOut])
def activity(
    space_id: uuid.UUID,
    current: FullAuth,
    db: DB,
    before: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ActivityOut]:
    spaces.access(db, current.user, space_id)
    query = (
        select(AuditEntry, User.display_name)
        .outerjoin(User, User.id == AuditEntry.actor_id)
        .where(AuditEntry.space_id == space_id, AuditEntry.action.in_(ACTIVITY_ACTIONS))
    )
    if before is not None:
        query = query.where(AuditEntry.id < before)
    rows = db.execute(query.order_by(AuditEntry.id.desc()).limit(limit)).tuples()
    return [
        ActivityOut(
            id=e.id,
            occurred_at=e.occurred_at,
            actor=name,
            action=e.action,
            # Solo datos que todos los miembros pueden ver: nunca IP ni navegador.
            detail={
                k: v
                for k, v in e.detail.items()
                if k
                in (
                    "count",
                    "name",
                    "album",
                    "uploaded",
                    "duplicates",
                    "kept",
                    "trashed",
                    "from",
                    "to",
                    "reason",
                    "action",
                )
            },
        )
        for e, name in rows
    ]
