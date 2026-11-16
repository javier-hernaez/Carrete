"""Rutas de etiquetas: «Personas», «Paisajes», «Humor»…"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import DB, FullAuth, ReqInfo
from app.services import spaces, tags

router = APIRouter(prefix="/api/v1", tags=["etiquetas"])


class TagOut(BaseModel):
    id: uuid.UUID
    name: str
    count: int


class TagIn(BaseModel):
    name: str = Field(max_length=200)
    asset_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5000)


class TagPatch(BaseModel):
    name: str = Field(max_length=200)


def _out(summary: tags.TagSummary) -> TagOut:
    return TagOut(id=summary.tag.id, name=summary.tag.name, count=summary.count)


def _one(db: DB, space_id: uuid.UUID, tag_id: uuid.UUID) -> TagOut:
    return next(_out(s) for s in tags.list_tags(db, space_id) if s.tag.id == tag_id)


@router.get("/spaces/{space_id}/tags", response_model=list[TagOut])
def list_tags(space_id: uuid.UUID, current: FullAuth, db: DB) -> list[TagOut]:
    spaces.access(db, current.user, space_id)
    return [_out(s) for s in tags.list_tags(db, space_id)]


@router.post("/spaces/{space_id}/tags", response_model=TagOut, status_code=201)
def create_tag(space_id: uuid.UUID, body: TagIn, current: FullAuth, db: DB, info: ReqInfo) -> TagOut:
    """Crea la etiqueta (o devuelve la que ya tiene ese nombre) y se la pone a los elementos que se den."""
    spaces.access(db, current.user, space_id, "collaborator")
    tag = tags.create(db, space_id, current.user, body.name, info)
    if body.asset_ids:
        tags.add_assets(db, tag, body.asset_ids, current.user.id)
    db.commit()
    return _one(db, space_id, tag.id)


@router.patch("/spaces/{space_id}/tags/{tag_id}", response_model=TagOut)
def rename_tag(
    space_id: uuid.UUID, tag_id: uuid.UUID, body: TagPatch, current: FullAuth, db: DB, info: ReqInfo
) -> TagOut:
    spaces.access(db, current.user, space_id, "collaborator")
    tags.rename(db, tags.get(db, space_id, tag_id), current.user, body.name, info)
    db.commit()
    return _one(db, space_id, tag_id)


@router.delete("/spaces/{space_id}/tags/{tag_id}", status_code=204)
def delete_tag(space_id: uuid.UUID, tag_id: uuid.UUID, current: FullAuth, db: DB, info: ReqInfo) -> None:
    """Eliminar una etiqueta nunca elimina fotos: solo se la quita a todas."""
    spaces.access(db, current.user, space_id, "collaborator")
    tags.remove(db, tags.get(db, space_id, tag_id), current.user, info)
    db.commit()
