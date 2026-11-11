"""Repetidas y parecidas.

Las idénticas no llegan a existir dentro de un espacio (un original solo puede estar una vez). Las casi
idénticas se detectan con la huella perceptual dHash de 64 bits: dos fotos son candidatas si la
distancia de Hamming entre sus huellas es como mucho ``CARRETE_DUPLICATE_DISTANCE`` (6 por defecto).
Cubre lo habitual: la misma foto reenviada por WhatsApp, en otra resolución, ráfagas, capturas repetidas.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import BigInteger, ColumnElement, and_, cast, delete, func, literal, or_, select, text
from sqlalchemy.dialects.postgresql import BIT, insert
from sqlalchemy.orm import Session

from app.db.models import AlbumAsset, Asset, Blob, DuplicateDismissal, DuplicateGroup, DuplicateMember, User
from app.services import audit, trash
from app.services.audit import RequestInfo
from app.services.errors import Invalid, NotFound
from app.services.spaces import SpaceAccess

OBVIOUS_DISTANCE = 2


def _hamming_sql(phash: int) -> ColumnElement[int]:
    # bit_count sobre el XOR de las dos huellas convertido a bit(64): se calcula en PostgreSQL.
    xor = Asset.phash.op("#")(literal(phash, BigInteger))
    return func.bit_count(cast(xor, BIT(64)))


def detect_for(db: Session, asset: Asset, max_distance: int) -> DuplicateGroup | None:
    """Busca parecidas de un elemento recién procesado y lo agrupa con ellas."""
    if asset.phash is None or asset.kind != "photo" or asset.trashed_at is not None:
        return None
    distance = _hamming_sql(asset.phash)
    dismissed = select(DuplicateDismissal).where(
        or_(
            and_(DuplicateDismissal.asset_a == asset.id, DuplicateDismissal.asset_b == Asset.id),
            and_(DuplicateDismissal.asset_b == asset.id, DuplicateDismissal.asset_a == Asset.id),
        )
    )
    rows = db.execute(
        select(Asset.id, distance.label("d"))
        .where(
            Asset.space_id == asset.space_id,
            Asset.id != asset.id,
            Asset.kind == "photo",
            Asset.phash.is_not(None),
            Asset.trashed_at.is_(None),
            distance <= max_distance,
            ~dismissed.exists(),
        )
        .order_by(text("d"))
        .limit(50)
    ).all()
    if not rows:
        return None
    candidates = [r[0] for r in rows]
    best = int(rows[0][1])
    group = db.scalar(
        select(DuplicateGroup)
        .join(DuplicateMember, DuplicateMember.group_id == DuplicateGroup.id)
        .where(DuplicateGroup.status == "pending", DuplicateMember.asset_id.in_([asset.id, *candidates]))
        .limit(1)
    )
    if group is None:
        group = DuplicateGroup(space_id=asset.space_id, kind="similar", distance=best)
        db.add(group)
        db.flush()
    else:
        group.distance = min(group.distance, best)
    for member in (asset.id, *candidates):
        db.execute(
            insert(DuplicateMember).values(group_id=group.id, asset_id=member).on_conflict_do_nothing()
        )
    return group


@dataclass
class Member:
    asset: Asset
    blob: Blob


def score(m: Member) -> tuple[int, int, int, int]:
    """Orden de preferencia: mayor resolución → tiene EXIF → mayor tamaño → no viene de WhatsApp."""
    pixels = (m.asset.width or 0) * (m.asset.height or 0)
    return (
        pixels,
        int(m.asset.taken_at_source == "exif"),
        m.blob.size_bytes,
        int(m.asset.source != "whatsapp"),
    )


def members(db: Session, group_id: uuid.UUID) -> list[Member]:
    rows = db.execute(
        select(Asset, Blob)
        .join(DuplicateMember, DuplicateMember.asset_id == Asset.id)
        .join(Blob, Blob.id == Asset.blob_id)
        .where(DuplicateMember.group_id == group_id, Asset.trashed_at.is_(None))
    ).tuples()
    return sorted((Member(a, b) for a, b in rows), key=score, reverse=True)


def pending_groups(
    db: Session, space_id: uuid.UUID, limit: int = 200
) -> list[tuple[DuplicateGroup, list[Member]]]:
    groups = db.scalars(
        select(DuplicateGroup)
        .where(DuplicateGroup.space_id == space_id, DuplicateGroup.status == "pending")
        .order_by(DuplicateGroup.created_at.desc())
        .limit(limit)
    )
    out = []
    for group in groups:
        found = members(db, group.id)
        if len(found) < 2:  # alguien ya eliminó a mano las demás: el grupo deja de tener sentido
            group.status = "resolved"
            group.resolved_at = datetime.now(UTC)
            continue
        out.append((group, found))
    return out


def get_group(db: Session, space_id: uuid.UUID, group_id: uuid.UUID) -> DuplicateGroup:
    group = db.get(DuplicateGroup, group_id)
    if group is None or group.space_id != space_id:
        raise NotFound("Ese grupo no existe")
    return group


def resolve(
    db: Session,
    acc: SpaceAccess,
    user: User,
    group: DuplicateGroup,
    keep: list[uuid.UUID],
    request: RequestInfo,
) -> list[uuid.UUID]:
    """Se queda con ``keep`` y manda las demás a la papelera. Las conservadas heredan álbumes,
    favorita y descripción de las descartadas. Devuelve las enviadas a la papelera."""
    found = members(db, group.id)
    ids = {m.asset.id for m in found}
    if not keep or not set(keep) <= ids:
        raise Invalid("Elige al menos una foto del grupo para conservar", code="invalid_keep")
    keepers = [m.asset for m in found if m.asset.id in keep]
    losers = [m.asset for m in found if m.asset.id not in keep]
    for keeper in keepers:
        for loser in losers:
            keeper.is_favorite = keeper.is_favorite or loser.is_favorite
            if not keeper.description and loser.description:
                keeper.description = loser.description
            if loser.review_state == "kept" and keeper.review_state == "pending":
                keeper.review_state = "kept"
        for album_id in set(
            db.scalars(
                select(AlbumAsset.album_id).where(AlbumAsset.asset_id.in_([loser.id for loser in losers]))
            )
        ):
            position = (
                db.scalar(select(func.max(AlbumAsset.position)).where(AlbumAsset.album_id == album_id)) or 0
            )
            db.execute(
                insert(AlbumAsset)
                .values(album_id=album_id, asset_id=keeper.id, position=position + 1, added_by=user.id)
                .on_conflict_do_nothing()
            )
    loser_ids = [loser.id for loser in losers]
    trash.move_to_trash(db, acc, user, loser_ids, request)
    group.status = "resolved"
    group.resolved_at = datetime.now(UTC)
    group.resolved_by = user.id
    audit.record(
        db,
        "duplicates.resolved",
        actor_id=user.id,
        space_id=acc.space.id,
        request=request,
        detail={"kept": len(keepers), "trashed": len(losers)},
    )
    return loser_ids


def reopen(db: Session, group: DuplicateGroup) -> None:
    group.status = "pending"
    group.resolved_at = None
    group.resolved_by = None


def dismiss(db: Session, acc: SpaceAccess, user: User, group: DuplicateGroup, request: RequestInfo) -> None:
    """«No son repetidas»: no se vuelven a proponer entre sí."""
    ids = sorted(m.asset.id for m in members(db, group.id))
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            db.execute(insert(DuplicateDismissal).values(asset_a=a, asset_b=b).on_conflict_do_nothing())
    group.status = "dismissed"
    group.resolved_at = datetime.now(UTC)
    group.resolved_by = user.id
    db.execute(delete(DuplicateMember).where(DuplicateMember.group_id == group.id))
    audit.record(
        db,
        "duplicates.dismissed",
        actor_id=user.id,
        space_id=acc.space.id,
        request=request,
        detail={"count": len(ids)},
    )


def obvious(db: Session, space_id: uuid.UUID) -> list[tuple[DuplicateGroup, Member, list[Member]]]:
    """Grupos evidentes: casi idénticos y con una mejor clara."""
    result = []
    for group, found in pending_groups(db, space_id):
        if group.distance > OBVIOUS_DISTANCE:
            continue
        best, rest = found[0], found[1:]
        if score(best) > score(rest[0]):
            result.append((group, best, rest))
    return result
