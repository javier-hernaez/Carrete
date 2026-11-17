"""Rutas de exportación, importaciones y biblioteca en disco."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DB, AdminAuth, FullAuth, ReqInfo, SettingsDep
from app.api.uploads import StorageDep
from app.db.models import Import
from app.jobs import queue
from app.services import auth, exports, spaces
from app.services.errors import NotFound

router = APIRouter(prefix="/api/v1", tags=["exportar"])


class ExportIn(BaseModel):
    structure: Literal["album", "date", "flat"] = "album"
    naming: Literal["original", "normalized"] = "normalized"
    include: Literal["kept", "kept_pending", "all"] = "kept_pending"
    ids: list[uuid.UUID] = Field(default_factory=list, max_length=10_000)
    album_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    all_albums: bool = False
    tag_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    target: Literal["zip", "folder"] = "zip"
    folder: str | None = Field(default=None, max_length=500)
    volume_bytes: int | None = Field(default=None, ge=100 * 1024 * 1024, le=100 * 1024**3)


class ExportOut(BaseModel):
    id: uuid.UUID
    state: str
    progress: float
    total_items: int
    total_bytes: int
    files: list[dict[str, Any]]
    params: dict[str, Any]
    error: str | None
    created_at: datetime
    expires_at: datetime
    mine: bool


def _out(export: Any, user_id: uuid.UUID) -> ExportOut:
    params = {k: v for k, v in export.params.items() if k not in ("ids",)}
    params["count_ids"] = len(export.params.get("ids") or [])
    return ExportOut(
        id=export.id,
        state=export.state,
        progress=export.progress,
        total_items=export.total_items,
        total_bytes=export.total_bytes,
        files=export.files,
        params=params,
        error=export.error,
        created_at=export.created_at,
        expires_at=export.expires_at,
        mine=export.requested_by == user_id,
    )


@router.post("/spaces/{space_id}/exports", response_model=ExportOut, status_code=201)
def create_export(
    space_id: uuid.UUID,
    body: ExportIn,
    current: FullAuth,
    db: DB,
    settings: SettingsDep,
    storage: StorageDep,
    info: ReqInfo,
) -> ExportOut:
    if not body.ids and not body.album_ids and not body.all_albums:
        # Exportar el espacio entero es una acción sensible.
        auth.require_recent_auth(current.session)
    params = body.model_dump(mode="json")
    export = exports.create(db, settings, storage, current.user, space_id, params, info)
    db.commit()
    return _out(export, current.user.id)


@router.get("/spaces/{space_id}/exports", response_model=list[ExportOut])
def list_exports(space_id: uuid.UUID, current: FullAuth, db: DB) -> list[ExportOut]:
    return [_out(e, current.user.id) for e in exports.list_for(db, current.user, space_id)]


@router.get("/spaces/{space_id}/exports/{export_id}", response_model=ExportOut)
def get_export(space_id: uuid.UUID, export_id: uuid.UUID, current: FullAuth, db: DB) -> ExportOut:
    return _out(exports.get(db, current.user, space_id, export_id), current.user.id)


@router.get("/spaces/{space_id}/exports/{export_id}/files/{number}", response_class=FileResponse)
def download_volume(
    space_id: uuid.UUID, export_id: uuid.UUID, number: int, current: FullAuth, db: DB, storage: StorageDep
) -> FileResponse:
    """Descarga reanudable (peticiones Range) de un volumen."""
    export = exports.get(db, current.user, space_id, export_id)
    entry = next((f for f in export.files if f.get("number") == number), None)
    path = exports.export_dir(storage, export.id) / f"{number:03d}.zip"
    if export.state != "ready" or entry is None or not path.is_file():
        raise NotFound("Ese volumen no existe o ha caducado")
    name = str(entry["name"])
    fallback = "".join(ch if ch.isascii() and (ch.isalnum() or ch in "._-() ") else "_" for ch in name)
    return FileResponse(
        path,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/spaces/{space_id}/exports/{export_id}", status_code=204)
def delete_export(
    space_id: uuid.UUID, export_id: uuid.UUID, current: FullAuth, db: DB, storage: StorageDep
) -> None:
    import shutil

    export = exports.get(db, current.user, space_id, export_id)
    shutil.rmtree(exports.export_dir(storage, export.id), ignore_errors=True)
    export.state = "expired"
    export.files = []
    db.commit()


class ImportOut(BaseModel):
    id: uuid.UUID
    name: str
    state: str
    counts: dict[str, Any]
    error: str | None
    created_at: datetime


@router.get("/spaces/{space_id}/imports", response_model=list[ImportOut])
def list_imports(space_id: uuid.UUID, current: FullAuth, db: DB) -> list[ImportOut]:
    spaces.access(db, current.user, space_id)
    rows = db.scalars(
        select(Import)
        .where(Import.space_id == space_id, Import.user_id == current.user.id)
        .order_by(Import.created_at.desc())
        .limit(20)
    )
    return [
        ImportOut(
            id=r.id, name=r.name, state=r.state, counts=r.counts, error=r.error, created_at=r.created_at
        )
        for r in rows
    ]


@router.post("/admin/library/rebuild", status_code=202)
def rebuild_library(current: AdminAuth, db: DB) -> dict[str, str]:
    queue.enqueue(db, "build_library", priority=150)
    db.commit()
    return {"status": "queued"}
