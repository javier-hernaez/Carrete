"""Rutas de elementos: comprobación previa a subir, línea temporal, detalle y ficheros."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DB, FullAuth, ReqInfo
from app.api.uploads import StorageDep
from app.db.models import AssetContribution, Blob, User
from app.services import assets as service
from app.services import audit, spaces
from app.services.errors import NotFound

router = APIRouter(prefix="/api/v1", tags=["elementos"])
log = logging.getLogger(__name__)

Review = Literal["pending", "kept", "discarded"]
Kind = Literal["photo", "video"]
Source = Literal["camera", "whatsapp", "screenshot", "other"]


class CheckIn(BaseModel):
    sha256: list[str] = Field(max_length=2000)


class CheckOut(BaseModel):
    present: list[str]


@router.post("/spaces/{space_id}/assets/check", response_model=CheckOut)
def check_hashes(space_id: uuid.UUID, body: CheckIn, current: FullAuth, db: DB) -> CheckOut:
    spaces.access(db, current.user, space_id)
    hashes = [h.lower() for h in body.sha256 if len(h) == 64]
    return CheckOut(present=service.present_hashes(db, space_id, hashes))


class UploadSummaryIn(BaseModel):
    uploaded: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    failed: int = Field(ge=0)


@router.post("/spaces/{space_id}/uploads/summary", status_code=204)
def upload_summary(
    space_id: uuid.UUID, body: UploadSummaryIn, current: FullAuth, db: DB, info: ReqInfo
) -> None:
    """Resumen de un lote de subidas para la auditoría y la actividad."""
    spaces.access(db, current.user, space_id, "collaborator")
    if body.uploaded or body.duplicates or body.failed:
        audit.record(
            db,
            "asset.uploaded",
            actor_id=current.user.id,
            space_id=space_id,
            request=info,
            detail=body.model_dump(),
        )
        db.commit()


class AssetOut(BaseModel):
    id: uuid.UUID
    kind: Kind
    taken_at: datetime
    taken_at_offset: int | None
    date_doubtful: bool
    width: int | None
    height: int | None
    duration_ms: int | None
    thumbhash: str | None
    review_state: Review
    is_favorite: bool
    processing_state: str
    source: Source
    tag_ids: list[uuid.UUID] = Field(default_factory=list)


def asset_out(a: object, tag_ids: list[uuid.UUID] | None = None) -> AssetOut:
    from app.db.models import Asset

    assert isinstance(a, Asset)
    return AssetOut(
        id=a.id,
        kind=a.kind,  # type: ignore[arg-type]
        taken_at=a.taken_at_local,
        taken_at_offset=a.taken_at_offset,
        date_doubtful=a.taken_at_source in service.DOUBTFUL_SOURCES,
        width=a.width,
        height=a.height,
        duration_ms=a.duration_ms,
        thumbhash=a.thumbhash,
        review_state=a.review_state,  # type: ignore[arg-type]
        is_favorite=a.is_favorite,
        processing_state=a.processing_state,
        source=a.source,  # type: ignore[arg-type]
        tag_ids=tag_ids or [],
    )


class AssetPage(BaseModel):
    items: list[AssetOut]
    next_cursor: str | None


def filters_dep(
    review: Annotated[list[Review] | None, Query()] = None,
    favorite: bool | None = None,
    kind: Kind | None = None,
    source: Source | None = None,
    uploaded_by: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    album_id: uuid.UUID | None = None,
    no_album: bool = False,
    tag_id: Annotated[list[uuid.UUID] | None, Query(max_length=10)] = None,
    no_tag: bool = False,
    doubtful: bool | None = None,
    trashed: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
    south: Annotated[float | None, Query(ge=-90, le=90)] = None,
    west: Annotated[float | None, Query(ge=-180, le=180)] = None,
    north: Annotated[float | None, Query(ge=-90, le=90)] = None,
    east: Annotated[float | None, Query(ge=-180, le=180)] = None,
    located: bool | None = None,
) -> service.Filters:
    return service.Filters(
        review=list(review) if review else None,
        favorite=favorite,
        kind=kind,
        source=source,
        uploaded_by=uploaded_by,
        date_from=date_from,
        date_to=date_to,
        album_id=album_id,
        no_album=no_album,
        tag_ids=list(tag_id) if tag_id else None,
        no_tag=no_tag,
        doubtful=doubtful,
        trashed=trashed,
        query=q.strip() if q else None,
        bounds=(south, west, north, east)
        if south is not None and west is not None and north is not None and east is not None
        else None,
        located=located,
    )


FiltersDep = Annotated[service.Filters, Depends(filters_dep)]


@router.get("/spaces/{space_id}/assets", response_model=AssetPage)
def list_assets(
    space_id: uuid.UUID,
    current: FullAuth,
    db: DB,
    filters: FiltersDep,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 300,
    order: Literal["desc", "asc", "album"] = "desc",
    start: date | None = None,
) -> AssetPage:
    spaces.access(db, current.user, space_id)
    if start is not None and cursor is None:
        cursor = service.cursor_for_date(db, space_id, filters, start)
    items, next_cursor = service.list_assets(db, space_id, filters, cursor=cursor, limit=limit, order=order)
    from app.services.tags import tag_ids_by_asset

    tags = tag_ids_by_asset(db, (a.id for a in items))
    return AssetPage(items=[asset_out(a, tags.get(a.id)) for a in items], next_cursor=next_cursor)


@router.get("/spaces/{space_id}/assets/random", response_model=AssetOut | None)
def random_asset(space_id: uuid.UUID, current: FullAuth, db: DB, filters: FiltersDep) -> AssetOut | None:
    """Un elemento al azar de todo el espacio (con o sin álbum), con los mismos filtros que la lista."""
    spaces.access(db, current.user, space_id)
    asset = service.random_asset(db, space_id, filters)
    if asset is None:
        return None
    from app.services.tags import tag_ids_by_asset

    return asset_out(asset, tag_ids_by_asset(db, [asset.id]).get(asset.id))


class MonthCount(BaseModel):
    year: int
    month: int
    count: int


class TimelineOut(BaseModel):
    total: int
    months: list[MonthCount]


@router.get("/spaces/{space_id}/timeline", response_model=TimelineOut)
def timeline(space_id: uuid.UUID, current: FullAuth, db: DB, filters: FiltersDep) -> TimelineOut:
    spaces.access(db, current.user, space_id)
    months = [MonthCount(year=y, month=m, count=c) for y, m, c in service.month_counts(db, space_id, filters)]
    return TimelineOut(total=sum(m.count for m in months), months=months)


class ContributorOut(BaseModel):
    display_name: str | None
    uploaded_at: datetime


class AssetDetail(AssetOut):
    space_id: uuid.UUID
    original_filename: str
    size_bytes: int
    mime: str
    sha256: str
    uploaded_by: str | None
    uploaded_at: datetime
    uploaded_via: str
    taken_at_source: str
    camera: str | None
    lat: float | None
    lon: float | None
    place_name: str | None
    place_region: str | None
    place_country: str | None
    description: str | None
    video_codec: str | None
    has_preview_video: bool
    processing_error: str | None
    contributors: list[ContributorOut]
    trashed_at: datetime | None
    albums: list[dict[str, str]]
    tags: list[dict[str, str]]


@router.get("/assets/{asset_id}", response_model=AssetDetail)
def get_asset(asset_id: uuid.UUID, current: FullAuth, db: DB) -> AssetDetail:
    asset, blob, _ = service.access_asset(db, current.user, asset_id)
    uploader = (
        db.scalar(select(User.display_name).where(User.id == asset.uploaded_by))
        if asset.uploaded_by
        else None
    )
    contributors = db.execute(
        select(User.display_name, AssetContribution.uploaded_at)
        .outerjoin(User, User.id == AssetContribution.user_id)
        .where(AssetContribution.asset_id == asset.id)
        .order_by(AssetContribution.uploaded_at)
    ).all()
    from app.services import albums, tags

    tag_list = tags.tags_of(db, asset.id)
    return AssetDetail(
        **asset_out(asset, [uuid.UUID(t["id"]) for t in tag_list]).model_dump(),
        space_id=asset.space_id,
        original_filename=asset.original_filename,
        size_bytes=blob.size_bytes,
        mime=blob.mime,
        sha256=blob.sha256,
        uploaded_by=uploader,
        uploaded_at=asset.created_at,
        uploaded_via=asset.uploaded_via,
        taken_at_source=asset.taken_at_source,
        camera=asset.camera,
        lat=asset.lat,
        lon=asset.lon,
        place_name=asset.place_name,
        place_region=asset.place_region,
        place_country=asset.place_country,
        description=asset.description,
        video_codec=asset.video_codec,
        has_preview_video=asset.has_preview_video,
        processing_error=asset.processing_error,
        contributors=[ContributorOut(display_name=n, uploaded_at=t) for n, t in contributors],
        trashed_at=asset.trashed_at,
        albums=albums.albums_of(db, asset.id),
        tags=tag_list,
    )


# --- Ficheros (siempre con sesión y pertenencia; caché privada) -----------------------------------------

PRIVATE_CACHE = "private, max-age=86400"


def _derivative(
    db: DB, current: FullAuth, storage: StorageDep, asset_id: uuid.UUID, name: str
) -> tuple[Path, Blob]:
    _, blob, _ = service.access_asset(db, current.user, asset_id)
    path = storage.derivative_dir(blob.sha256) / name
    if not path.is_file():
        raise NotFound("Aún se está procesando", code="not_ready")
    return path, blob


@router.get("/assets/{asset_id}/thumb", response_class=FileResponse)
def thumb(asset_id: uuid.UUID, current: FullAuth, db: DB, storage: StorageDep) -> FileResponse:
    path, _ = _derivative(db, current, storage, asset_id, "thumb.webp")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": PRIVATE_CACHE})


@router.get("/assets/{asset_id}/preview", response_class=FileResponse)
def preview(asset_id: uuid.UUID, current: FullAuth, db: DB, storage: StorageDep) -> FileResponse:
    path, _ = _derivative(db, current, storage, asset_id, "preview.webp")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": PRIVATE_CACHE})


@router.get("/assets/{asset_id}/video", response_class=FileResponse)
def video(asset_id: uuid.UUID, current: FullAuth, db: DB, storage: StorageDep) -> FileResponse:
    """Vídeo reproducible: la versión convertida si hizo falta o el original si ya valía."""
    asset, blob, _ = service.access_asset(db, current.user, asset_id)
    if asset.kind != "video":
        raise NotFound("No es un vídeo")
    if asset.has_preview_video:
        path = storage.derivative_dir(blob.sha256) / "video.mp4"
        media_type = "video/mp4"
    else:
        path = storage.original_path(blob.sha256, blob.ext)
        media_type = blob.mime
    if not path.is_file():
        raise NotFound("Aún se está procesando", code="not_ready")
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": PRIVATE_CACHE})


@router.get("/assets/{asset_id}/original", response_class=FileResponse)
def original(asset_id: uuid.UUID, current: FullAuth, db: DB, storage: StorageDep) -> FileResponse:
    """Descarga del original sin tocar. Siempre como adjunto: nunca se interpreta en el navegador."""
    asset, blob, _ = service.access_asset(db, current.user, asset_id)
    path = storage.original_path(blob.sha256, blob.ext)
    if not path.is_file():
        raise NotFound("No se encuentra el original")
    name = asset.original_filename
    fallback = (
        "".join(ch if (ch.isascii() and ch.isalnum()) or ch in "._-" else "_" for ch in name) or "original"
    )
    disposition = f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"
    return FileResponse(
        path,
        media_type=blob.mime,
        headers={"Content-Disposition": disposition, "Cache-Control": "private, no-store"},
    )


# --- Acciones masivas y papelera -----------------------------------------------------------------------

BatchAction = Literal[
    "trash",
    "restore",
    "review",
    "favorite",
    "add_album",
    "remove_album",
    "add_tag",
    "remove_tag",
    "set_date",
    "shift_date",
    "revert",
    "set_location",
]


class BatchIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=5000)
    action: BatchAction
    state: Review | None = None
    value: bool | None = None
    album_id: uuid.UUID | None = None
    tag_id: uuid.UUID | None = None
    taken_at: str | None = Field(default=None, max_length=40)
    offset_minutes: int | None = None
    minutes: int | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    snapshot: dict[str, dict[str, object]] | None = None


class CountOut(BaseModel):
    count: int


class BatchOut(CountOut):
    undo: dict[str, object] | None = None


@router.post("/spaces/{space_id}/assets/batch", response_model=BatchOut)
def batch(space_id: uuid.UUID, body: BatchIn, current: FullAuth, db: DB, info: ReqInfo) -> BatchOut:
    from app.services import batch as batch_service

    params = body.model_dump(exclude={"ids", "action"}, exclude_unset=True, mode="json")
    count, undo = batch_service.apply(db, current.user, space_id, body.ids, body.action, params, info)
    db.commit()
    # Qué se pidió y cuántos cambiaron: sin esto no se distingue «no llegó» de «no cambió nada».
    log.info("Acción en lote", extra={"action": body.action, "requested": len(body.ids), "changed": count})
    return BatchOut(count=count, undo=undo)


class AssetPatch(BaseModel):
    description: str | None = Field(default=None, max_length=2000)


@router.patch("/assets/{asset_id}", status_code=204)
def update_asset(asset_id: uuid.UUID, body: AssetPatch, current: FullAuth, db: DB) -> None:
    """Descripción de texto libre."""
    asset, _, _ = service.access_asset(db, current.user, asset_id, "collaborator")
    if body.description is not None:
        asset.description = body.description.strip() or None
    db.commit()


class CountersOut(BaseModel):
    pending_review: int
    duplicates: int
    discarded: int
    trash: int


@router.get("/spaces/{space_id}/counters", response_model=CountersOut)
def counters(space_id: uuid.UUID, current: FullAuth, db: DB) -> CountersOut:
    """Lo que falta por hacer: «312 sin revisar», «8 grupos de repetidas»."""
    from sqlalchemy import func

    from app.db.models import Asset, DuplicateGroup

    spaces.access(db, current.user, space_id)
    alive = (Asset.space_id == space_id) & Asset.trashed_at.is_(None)
    by_state = dict(
        db.execute(select(Asset.review_state, func.count()).where(alive).group_by(Asset.review_state))
        .tuples()
        .all()
    )
    groups = (
        db.scalar(
            select(func.count()).where(
                DuplicateGroup.space_id == space_id, DuplicateGroup.status == "pending"
            )
        )
        or 0
    )
    trashed = (
        db.scalar(select(func.count()).where(Asset.space_id == space_id, Asset.trashed_at.is_not(None))) or 0
    )
    return CountersOut(
        pending_review=int(by_state.get("pending", 0)),
        duplicates=int(groups),
        discarded=int(by_state.get("discarded", 0)),
        trash=int(trashed),
    )


class EmptyTrashIn(BaseModel):
    confirm_name: str = Field(max_length=200)


@router.get("/spaces/{space_id}/trash", response_model=CountOut)
def trash_count(space_id: uuid.UUID, current: FullAuth, db: DB) -> CountOut:
    from app.services import trash

    spaces.access(db, current.user, space_id)
    return CountOut(count=trash.trash_count(db, space_id))


@router.post("/spaces/{space_id}/trash/empty", response_model=CountOut)
def empty_trash(
    space_id: uuid.UUID, body: EmptyTrashIn, current: FullAuth, db: DB, storage: StorageDep, info: ReqInfo
) -> CountOut:
    from app.services import auth, trash

    acc = spaces.access(db, current.user, space_id, "owner")
    auth.require_recent_auth(current.session)
    count = trash.empty(db, storage, acc, current.user, body.confirm_name, info)
    db.commit()
    return CountOut(count=count)
