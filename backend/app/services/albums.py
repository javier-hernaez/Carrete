"""Álbumes: crear, renombrar, portada, descripción, orden por fecha o manual, eliminar.

Eliminar un álbum nunca elimina sus elementos. El orden manual usa un índice fraccionario: insertar
entre dos elementos es tomar el punto medio de sus posiciones, sin reescribir el resto.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Album, AlbumAsset, Asset, User
from app.services import audit
from app.services.audit import RequestInfo
from app.services.errors import Invalid, NotFound

if TYPE_CHECKING:
    from app.services.assets import Filters

AnySelect = Select[*tuple[Any, ...]]

MAX_NAME = 120
MIN_GAP = 1e-9


def apply_album_filter(stmt: AnySelect, f: Filters) -> AnySelect:
    if f.album_id is not None:
        stmt = stmt.where(Asset.id.in_(select(AlbumAsset.asset_id).where(AlbumAsset.album_id == f.album_id)))
    if f.no_album:
        stmt = stmt.where(Asset.id.not_in(select(AlbumAsset.asset_id)))
    return stmt


def get(db: Session, space_id: uuid.UUID, album_id: uuid.UUID) -> Album:
    album = db.get(Album, album_id)
    if album is None or album.space_id != space_id:
        raise NotFound("Ese álbum no existe")
    return album


def _clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise Invalid("El álbum necesita un nombre", code="invalid_name")
    return name[:MAX_NAME]


@dataclass
class AlbumSummary:
    album: Album
    count: int
    cover_asset_id: uuid.UUID | None
    first: datetime | None
    last: datetime | None


def list_albums(db: Session, space_id: uuid.UUID) -> list[AlbumSummary]:
    visible = and_(Asset.trashed_at.is_(None), Asset.review_state != "discarded")
    stats = (
        select(
            AlbumAsset.album_id.label("album_id"),
            func.count().label("count"),
            func.min(Asset.taken_at_local).label("first"),
            func.max(Asset.taken_at_local).label("last"),
            # Portada por defecto: el elemento más reciente del álbum.
            (func.array_agg(Asset.id).filter(visible)).label("ids"),
        )
        .join(Asset, Asset.id == AlbumAsset.asset_id)
        .where(visible)
        .group_by(AlbumAsset.album_id)
        .subquery()
    )
    rows = db.execute(
        select(Album, stats.c.count, stats.c.first, stats.c.last, stats.c.ids)
        .outerjoin(stats, stats.c.album_id == Album.id)
        .where(Album.space_id == space_id)
        .order_by(stats.c.last.desc().nulls_last(), Album.name)
    ).all()
    result = []
    for album, count, first, last, ids in rows:
        cover = album.cover_asset_id or (_latest(db, album.id) if ids else None)
        result.append(AlbumSummary(album, int(count or 0), cover, first, last))
    return result


def _latest(db: Session, album_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(Asset.id)
        .join(AlbumAsset, AlbumAsset.asset_id == Asset.id)
        .where(AlbumAsset.album_id == album_id, Asset.trashed_at.is_(None), Asset.review_state != "discarded")
        .order_by(Asset.taken_at_local.desc())
        .limit(1)
    )


def create(
    db: Session, space_id: uuid.UUID, user: User, name: str, description: str | None, request: RequestInfo
) -> Album:
    album = Album(
        space_id=space_id, name=_clean_name(name), description=(description or None), created_by=user.id
    )
    db.add(album)
    db.flush()
    audit.record(
        db,
        "album.created",
        actor_id=user.id,
        space_id=space_id,
        target_type="album",
        target_id=album.id,
        request=request,
        detail={"name": album.name},
    )
    return album


def update(
    db: Session,
    album: Album,
    user: User,
    *,
    name: str | None,
    description: str | None,
    cover_asset_id: uuid.UUID | None,
    sort_mode: str | None,
    request: RequestInfo,
) -> None:
    changes: dict[str, Any] = {}
    if name is not None and _clean_name(name) != album.name:
        changes["name"] = {"from": album.name, "to": _clean_name(name)}
        album.name = _clean_name(name)
    if description is not None:
        album.description = description.strip() or None
    if cover_asset_id is not None:
        if (
            db.scalar(
                select(AlbumAsset.asset_id).where(
                    AlbumAsset.album_id == album.id, AlbumAsset.asset_id == cover_asset_id
                )
            )
            is None
        ):
            raise Invalid("La portada tiene que ser una foto del álbum", code="invalid_cover")
        album.cover_asset_id = cover_asset_id
    if sort_mode is not None:
        album.sort_mode = sort_mode
    if changes:
        audit.record(
            db,
            "album.renamed",
            actor_id=user.id,
            space_id=album.space_id,
            target_type="album",
            target_id=album.id,
            request=request,
            detail=changes,
        )


def remove(db: Session, album: Album, user: User, request: RequestInfo) -> None:
    audit.record(
        db,
        "album.deleted",
        actor_id=user.id,
        space_id=album.space_id,
        target_type="album",
        target_id=album.id,
        request=request,
        detail={"name": album.name},
    )
    db.delete(album)  # album_assets se borra en cascada; los elementos no se tocan


def _next_position(db: Session, album_id: uuid.UUID) -> float:
    current = db.scalar(select(func.max(AlbumAsset.position)).where(AlbumAsset.album_id == album_id))
    return float(current or 0) + 1.0


def add_assets(db: Session, album: Album, ids: list[uuid.UUID], user_id: uuid.UUID | None) -> int:
    """Añade al final (en el orden dado). Solo elementos del mismo espacio; los repetidos se ignoran."""
    valid = list(db.scalars(select(Asset.id).where(Asset.space_id == album.space_id, Asset.id.in_(ids))))
    order = {i: n for n, i in enumerate(ids)}
    valid.sort(key=lambda i: order.get(i, 0))
    start = _next_position(db, album.id)
    added = 0
    for offset, asset_id in enumerate(valid):
        inserted = db.execute(
            insert(AlbumAsset)
            .values(album_id=album.id, asset_id=asset_id, position=start + offset, added_by=user_id)
            .on_conflict_do_nothing()
            .returning(AlbumAsset.asset_id)
        ).first()
        added += inserted is not None
    return added


def remove_assets(db: Session, album: Album, ids: list[uuid.UUID]) -> int:
    result = db.execute(
        delete(AlbumAsset).where(AlbumAsset.album_id == album.id, AlbumAsset.asset_id.in_(ids))
    )
    if album.cover_asset_id in ids:
        album.cover_asset_id = None
    return int(result.rowcount)  # type: ignore[attr-defined]


def reorder(
    db: Session, album: Album, asset_id: uuid.UUID, *, after_id: uuid.UUID | None, before_id: uuid.UUID | None
) -> None:
    """Coloca ``asset_id`` entre ``after_id`` y ``before_id`` (cualquiera puede faltar: extremo)."""
    links = {
        link.asset_id: link
        for link in db.scalars(
            select(AlbumAsset).where(
                AlbumAsset.album_id == album.id,
                AlbumAsset.asset_id.in_([i for i in (asset_id, after_id, before_id) if i]),
            )
        )
    }
    moving = links.get(asset_id)
    if moving is None or (after_id and after_id not in links) or (before_id and before_id not in links):
        raise NotFound("Ese elemento no está en el álbum")
    low = links[after_id].position if after_id else None
    high = links[before_id].position if before_id else None
    if low is None and high is None:
        return
    if low is None:
        assert high is not None
        low = high - 2.0
    if high is None:
        high = low + 2.0
    if high - low < MIN_GAP:
        _renumber(db, album.id)
        return reorder(db, album, asset_id, after_id=after_id, before_id=before_id)
    moving.position = (low + high) / 2
    album.sort_mode = "manual"
    return None


def _renumber(db: Session, album_id: uuid.UUID) -> None:
    links = list(
        db.scalars(select(AlbumAsset).where(AlbumAsset.album_id == album_id).order_by(AlbumAsset.position))
    )
    for n, link in enumerate(links, 1):
        link.position = float(n)
    db.flush()


def manual_order(stmt: AnySelect, album_id: uuid.UUID) -> AnySelect:
    return stmt.join(
        AlbumAsset, and_(AlbumAsset.asset_id == Asset.id, AlbumAsset.album_id == album_id)
    ).order_by(AlbumAsset.position, Asset.id)


def add_on_upload(db: Session, space_id: uuid.UUID, album_id: uuid.UUID, asset_id: uuid.UUID) -> None:
    """Álbum elegido al subir: entra en el álbum y sigue «sin revisar»."""
    album = db.get(Album, album_id)
    if album is not None and album.space_id == space_id:
        add_assets(db, album, [asset_id], None)


def albums_of(db: Session, asset_id: uuid.UUID) -> list[dict[str, str]]:
    rows = db.execute(
        select(Album.id, Album.name)
        .join(AlbumAsset, AlbumAsset.album_id == Album.id)
        .where(AlbumAsset.asset_id == asset_id)
        .order_by(Album.name)
    ).all()
    return [{"id": str(i), "name": n} for i, n in rows]


def album_names_by_asset(db: Session, space_id: uuid.UUID) -> dict[Any, list[str]]:
    result: dict[Any, list[str]] = {}
    rows = db.execute(
        select(AlbumAsset.asset_id, Album.name)
        .join(Album, Album.id == AlbumAsset.album_id)
        .where(Album.space_id == space_id)
        .order_by(Album.name)
    ).all()
    for asset_id, name in rows:
        result.setdefault(asset_id, []).append(name)
    return result


def membership(db: Session, album_id: uuid.UUID, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(AlbumAsset.asset_id).where(AlbumAsset.album_id == album_id, AlbumAsset.asset_id.in_(ids))
        )
    )
