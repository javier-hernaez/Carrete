"""Elementos (fotos y vídeos): alta tras una subida, listado de la línea temporal y detalle."""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Asset, AssetContribution, Blob, Membership, User
from app.ids import uuid7
from app.jobs import queue
from app.media import dates
from app.media.sniff import FileType
from app.services.errors import Invalid, NotFound

AnySelect = Select[*tuple[Any, ...]]


def access_asset(
    db: Session, user: User, asset_id: uuid.UUID, minimum: str = "viewer"
) -> tuple[Asset, Blob, str]:
    """Carga un elemento comprobando que la persona es miembro de su espacio. 404 si no."""
    from app.services.spaces import RANK

    row = db.execute(
        select(Asset, Blob, Membership.role)
        .join(Blob, Blob.id == Asset.blob_id)
        .join(Membership, and_(Membership.space_id == Asset.space_id, Membership.user_id == user.id))
        .where(Asset.id == asset_id)
    ).first()
    if row is None:
        raise NotFound("Esa foto no existe")
    asset, blob, role = row.tuple()
    if RANK[role] < RANK[minimum]:
        from app.services.errors import Forbidden

        raise Forbidden("Con el rol de lector no puedes hacer cambios en este espacio")
    return asset, blob, role


@dataclass
class Registered:
    asset: Asset
    duplicate: bool


def register(
    db: Session,
    *,
    space_id: uuid.UUID,
    user_id: uuid.UUID,
    sha256: str,
    size: int,
    file_type: FileType,
    filename: str,
    relative_path: str | None,
    client_mtime_ms: int | None,
    uploaded_via: str,
) -> Registered:
    """Da de alta un original ya guardado en disco como elemento del espacio (o anota la aportación)."""
    db.execute(
        insert(Blob)
        .values(id=uuid7(), sha256=sha256, size_bytes=size, mime=file_type.mime, ext=file_type.ext)
        .on_conflict_do_nothing(index_elements=["sha256"])
    )
    blob = db.scalar(select(Blob).where(Blob.sha256 == sha256).with_for_update())
    assert blob is not None
    # Si el original estaba esperando su purga (o ya se purgó y se vuelve a subir), vuelve a estar en uso.
    blob.purge_after = None
    if blob.purged_at is not None:
        blob.purged_at = None
        blob.backed_up_at = None

    existing = db.scalar(select(Asset).where(Asset.space_id == space_id, Asset.blob_id == blob.id))
    if existing is not None:
        db.add(AssetContribution(asset_id=existing.id, user_id=user_id, original_filename=filename))
        if existing.trashed_at is not None:  # volver a subir algo de la papelera lo recupera
            existing.trashed_at = None
            existing.trashed_by = None
        return Registered(existing, duplicate=True)

    now = datetime.now(UTC)
    first = dates.deduce(filename=filename, client_mtime_ms=client_mtime_ms, uploaded_at=now)
    asset = Asset(
        space_id=space_id,
        blob_id=blob.id,
        kind=file_type.kind,
        original_filename=filename,
        relative_path=relative_path,
        uploaded_by=user_id,
        uploaded_via=uploaded_via,
        source=dates.deduce_source(filename, camera=None, has_exif_date=False),
        taken_at_local=first.local,
        taken_at_offset=first.offset_minutes,
        taken_at_source=first.source,
        client_mtime_ms=client_mtime_ms,
    )
    db.add(asset)
    blob.ref_count += 1
    db.flush()
    db.add(AssetContribution(asset_id=asset.id, user_id=user_id, original_filename=filename))
    queue.enqueue(db, "process_asset", {"asset_id": str(asset.id)}, priority=50)
    return Registered(asset, duplicate=False)


def present_hashes(db: Session, space_id: uuid.UUID, hashes: list[str]) -> list[str]:
    """Qué SHA-256 ya están en este espacio (no en otros: no se revela nada ajeno)."""
    if not hashes:
        return []
    rows = db.scalars(
        select(Blob.sha256)
        .join(Asset, Asset.blob_id == Blob.id)
        .where(Asset.space_id == space_id, Asset.trashed_at.is_(None), Blob.sha256.in_(hashes))
    )
    return sorted(set(rows))


# --- Línea temporal ------------------------------------------------------------------------------------


@dataclass
class Filters:
    review: list[str] | None = None  # por defecto: todo menos descartadas
    favorite: bool | None = None
    kind: str | None = None
    source: str | None = None
    uploaded_by: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    album_id: uuid.UUID | None = None
    no_album: bool = False
    doubtful: bool | None = None
    trashed: bool = False
    query: str | None = None


DOUBTFUL_SOURCES = ("mtime", "upload")


def apply_filters(stmt: AnySelect, space_id: uuid.UUID, f: Filters) -> AnySelect:
    stmt = stmt.where(Asset.space_id == space_id)
    stmt = stmt.where(Asset.trashed_at.is_not(None) if f.trashed else Asset.trashed_at.is_(None))
    if f.review:
        stmt = stmt.where(Asset.review_state.in_(f.review))
    elif not f.trashed:
        stmt = stmt.where(Asset.review_state != "discarded")
    if f.favorite is not None:
        stmt = stmt.where(Asset.is_favorite.is_(f.favorite))
    if f.kind:
        stmt = stmt.where(Asset.kind == f.kind)
    if f.source:
        stmt = stmt.where(Asset.source == f.source)
    if f.uploaded_by:
        stmt = stmt.where(Asset.uploaded_by == f.uploaded_by)
    if f.date_from:
        stmt = stmt.where(Asset.taken_at_local >= datetime.combine(f.date_from, time.min))
    if f.date_to:
        stmt = stmt.where(Asset.taken_at_local <= datetime.combine(f.date_to, time.max))
    if f.doubtful is not None:
        cond = Asset.taken_at_source.in_(DOUBTFUL_SOURCES)
        stmt = stmt.where(cond if f.doubtful else ~cond)
    if f.query:
        like = f"%{f.query.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(or_(Asset.original_filename.ilike(like), Asset.description.ilike(like)))
    from app.services import albums as album_service

    return album_service.apply_album_filter(stmt, f)


def encode_cursor(asset: Asset) -> str:
    raw = f"{asset.taken_at_local.isoformat()}|{asset.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        when, ident = raw.split("|")
        return datetime.fromisoformat(when), uuid.UUID(ident)
    except (ValueError, UnicodeDecodeError) as exc:
        raise Invalid("Cursor no válido", code="invalid_cursor") from exc


def list_assets(
    db: Session, space_id: uuid.UUID, f: Filters, *, cursor: str | None, limit: int, order: str = "desc"
) -> tuple[list[Asset], str | None]:
    if f.album_id is not None and order == "album":
        return _list_manual(db, space_id, f, cursor=cursor, limit=limit)
    stmt = apply_filters(select(Asset), space_id, f)
    if cursor:
        when, ident = decode_cursor(cursor)
        if order == "desc":
            stmt = stmt.where(
                or_(Asset.taken_at_local < when, and_(Asset.taken_at_local == when, Asset.id < ident))
            )
        else:
            stmt = stmt.where(
                or_(Asset.taken_at_local > when, and_(Asset.taken_at_local == when, Asset.id > ident))
            )
    if order == "desc":
        stmt = stmt.order_by(Asset.taken_at_local.desc(), Asset.id.desc())
    else:
        stmt = stmt.order_by(Asset.taken_at_local.asc(), Asset.id.asc())
    rows = list(db.scalars(stmt.limit(limit + 1)))
    next_cursor = encode_cursor(rows[limit - 1]) if len(rows) > limit else None
    return rows[:limit], next_cursor


def month_counts(db: Session, space_id: uuid.UUID, f: Filters) -> list[tuple[int, int, int]]:
    """(año, mes, número) para la barra de fechas, de lo más reciente a lo más antiguo."""
    year = func.extract("year", Asset.taken_at_local)
    month = func.extract("month", Asset.taken_at_local)
    stmt = apply_filters(select(year, month, func.count()), space_id, f).group_by(year, month)
    rows = db.execute(stmt.order_by(year.desc(), month.desc())).all()
    return [(int(y), int(m), int(c)) for y, m, c in rows]


def cursor_for_date(db: Session, space_id: uuid.UUID, f: Filters, before: date) -> str | None:
    """Cursor para empezar la línea temporal en una fecha (saltar a un año o un mes)."""
    limit = datetime.combine(before, time.max)
    first = db.scalar(
        apply_filters(select(Asset), space_id, f)
        .where(Asset.taken_at_local > limit)
        .order_by(Asset.taken_at_local.asc(), Asset.id.asc())
        .limit(1)
    )
    return encode_cursor(first) if first is not None else None


def mark_processing_failed(db: Session, asset_id: uuid.UUID, error: str) -> None:
    db.execute(
        update(Asset)
        .where(Asset.id == asset_id)
        .values(processing_state="failed", processing_error=error[:1000])
    )


def _list_manual(
    db: Session, space_id: uuid.UUID, f: Filters, *, cursor: str | None, limit: int
) -> tuple[list[Asset], str | None]:
    """Álbum en orden manual: por posición. El cursor es un desplazamiento (los álbumes son pequeños)."""
    from app.services import albums

    assert f.album_id is not None
    album = albums.get(db, space_id, f.album_id)
    offset = int(cursor[2:]) if cursor and cursor.startswith("o:") and cursor[2:].isdigit() else 0
    stmt = albums.manual_order(apply_filters(select(Asset), space_id, f), album.id)
    rows = list(db.scalars(stmt.offset(offset).limit(limit + 1)))
    return rows[:limit], (f"o:{offset + limit}" if len(rows) > limit else None)
