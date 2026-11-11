"""Rutas de álbumes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import DB, FullAuth, ReqInfo
from app.services import albums, spaces

router = APIRouter(prefix="/api/v1", tags=["álbumes"])


class AlbumOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    count: int
    cover_asset_id: uuid.UUID | None
    sort_mode: Literal["date", "manual"]
    first: datetime | None
    last: datetime | None


class AlbumIn(BaseModel):
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    asset_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5000)


class AlbumPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    cover_asset_id: uuid.UUID | None = None
    sort_mode: Literal["date", "manual"] | None = None


class ReorderIn(BaseModel):
    asset_id: uuid.UUID
    after_id: uuid.UUID | None = None
    before_id: uuid.UUID | None = None


def _out(summary: albums.AlbumSummary) -> AlbumOut:
    a = summary.album
    return AlbumOut(
        id=a.id,
        name=a.name,
        description=a.description,
        count=summary.count,
        cover_asset_id=summary.cover_asset_id,
        sort_mode=a.sort_mode,  # type: ignore[arg-type]
        first=summary.first,
        last=summary.last,
    )


@router.get("/spaces/{space_id}/albums", response_model=list[AlbumOut])
def list_albums(space_id: uuid.UUID, current: FullAuth, db: DB) -> list[AlbumOut]:
    spaces.access(db, current.user, space_id)
    return [_out(s) for s in albums.list_albums(db, space_id)]


@router.post("/spaces/{space_id}/albums", response_model=AlbumOut, status_code=201)
def create_album(space_id: uuid.UUID, body: AlbumIn, current: FullAuth, db: DB, info: ReqInfo) -> AlbumOut:
    spaces.access(db, current.user, space_id, "collaborator")
    album = albums.create(db, space_id, current.user, body.name, body.description, info)
    if body.asset_ids:
        albums.add_assets(db, album, body.asset_ids, current.user.id)
    db.commit()
    return next(_out(s) for s in albums.list_albums(db, space_id) if s.album.id == album.id)


@router.get("/spaces/{space_id}/albums/{album_id}", response_model=AlbumOut)
def get_album(space_id: uuid.UUID, album_id: uuid.UUID, current: FullAuth, db: DB) -> AlbumOut:
    spaces.access(db, current.user, space_id)
    albums.get(db, space_id, album_id)
    return next(_out(s) for s in albums.list_albums(db, space_id) if s.album.id == album_id)


@router.patch("/spaces/{space_id}/albums/{album_id}", response_model=AlbumOut)
def update_album(
    space_id: uuid.UUID, album_id: uuid.UUID, body: AlbumPatch, current: FullAuth, db: DB, info: ReqInfo
) -> AlbumOut:
    spaces.access(db, current.user, space_id, "collaborator")
    album = albums.get(db, space_id, album_id)
    albums.update(
        db,
        album,
        current.user,
        name=body.name,
        description=body.description,
        cover_asset_id=body.cover_asset_id,
        sort_mode=body.sort_mode,
        request=info,
    )
    db.commit()
    return get_album(space_id, album_id, current, db)


@router.delete("/spaces/{space_id}/albums/{album_id}", status_code=204)
def delete_album(space_id: uuid.UUID, album_id: uuid.UUID, current: FullAuth, db: DB, info: ReqInfo) -> None:
    """Eliminar un álbum nunca elimina sus fotos."""
    spaces.access(db, current.user, space_id, "collaborator")
    albums.remove(db, albums.get(db, space_id, album_id), current.user, info)
    db.commit()


@router.post("/spaces/{space_id}/albums/{album_id}/reorder", status_code=204)
def reorder(space_id: uuid.UUID, album_id: uuid.UUID, body: ReorderIn, current: FullAuth, db: DB) -> None:
    spaces.access(db, current.user, space_id, "collaborator")
    albums.reorder(
        db,
        albums.get(db, space_id, album_id),
        body.asset_id,
        after_id=body.after_id,
        before_id=body.before_id,
    )
    db.commit()
