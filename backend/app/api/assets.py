"""Rutas de elementos: comprobación previa a subir, línea temporal, detalle y ficheros."""

from __future__ import annotations

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


def asset_out(a: object) -> AssetOut:
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
    doubtful: bool | None = None,
    trashed: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
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
        doubtful=doubtful,
        trashed=trashed,
        query=q.strip() if q else None,
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
    order: Literal["desc", "asc"] = "desc",
    start: date | None = None,
) -> AssetPage:
    spaces.access(db, current.user, space_id)
    if start is not None and cursor is None:
        cursor = service.cursor_for_date(db, space_id, filters, start)
    items, next_cursor = service.list_assets(db, space_id, filters, cursor=cursor, limit=limit, order=order)
    return AssetPage(items=[asset_out(a) for a in items], next_cursor=next_cursor)


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
    description: str | None
    video_codec: str | None
    has_preview_video: bool
    processing_error: str | None
    contributors: list[ContributorOut]
    trashed_at: datetime | None
    albums: list[dict[str, str]]


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
    from app.services import albums

    return AssetDetail(
        **asset_out(asset).model_dump(),
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
        description=asset.description,
        video_codec=asset.video_codec,
        has_preview_video=asset.has_preview_video,
        processing_error=asset.processing_error,
        contributors=[ContributorOut(display_name=n, uploaded_at=t) for n, t in contributors],
        trashed_at=asset.trashed_at,
        albums=albums.albums_of(db, asset.id),
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
