"""Etiquetas: «Personas», «Paisajes», «Humor»… Una foto puede tener varias.

Complementan a los álbumes: un álbum es un conjunto ordenado con portada (un viaje, una boda); una
etiqueta es una marca rápida que atraviesa álbumes y fechas. Eliminar una etiqueta nunca elimina fotos.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Asset, AssetTag, Tag, User
from app.services import audit
from app.services.audit import RequestInfo
from app.services.errors import Conflict, Invalid, NotFound

if TYPE_CHECKING:
    from app.services.assets import Filters

AnySelect = Select[*tuple[Any, ...]]

MAX_NAME = 40
MAX_TAGS = 200


def clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise Invalid("La etiqueta necesita un nombre", code="invalid_name")
    if len(name) > MAX_NAME:
        raise Invalid(f"Como mucho {MAX_NAME} caracteres", code="invalid_name")
    return name


def key_of(name: str) -> str:
    return clean_name(name).casefold()


def apply_tag_filter(stmt: AnySelect, f: Filters) -> AnySelect:
    # Varias etiquetas: elementos que tienen todas (lo esperable al ir afinando: «Personas» y «Humor»).
    for tag_id in f.tag_ids or []:
        stmt = stmt.where(Asset.id.in_(select(AssetTag.asset_id).where(AssetTag.tag_id == tag_id)))
    if f.no_tag:
        stmt = stmt.where(Asset.id.not_in(select(AssetTag.asset_id)))
    return stmt


def get(db: Session, space_id: uuid.UUID, tag_id: uuid.UUID) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None or tag.space_id != space_id:
        raise NotFound("Esa etiqueta no existe")
    return tag


@dataclass
class TagSummary:
    tag: Tag
    count: int


def list_tags(db: Session, space_id: uuid.UUID) -> list[TagSummary]:
    """Etiquetas del espacio con cuántos elementos visibles tiene cada una, por nombre."""
    visible = and_(Asset.trashed_at.is_(None), Asset.review_state != "discarded")
    counts = (
        select(AssetTag.tag_id.label("tag_id"), func.count().label("count"))
        .join(Asset, Asset.id == AssetTag.asset_id)
        .where(visible)
        .group_by(AssetTag.tag_id)
        .subquery()
    )
    rows = db.execute(
        select(Tag, counts.c.count)
        .outerjoin(counts, counts.c.tag_id == Tag.id)
        .where(Tag.space_id == space_id)
        .order_by(Tag.key)
    ).all()
    return [TagSummary(tag, int(count or 0)) for tag, count in rows]


def create(db: Session, space_id: uuid.UUID, user: User, name: str, request: RequestInfo) -> Tag:
    """Crea la etiqueta; si ya existe con otro uso de mayúsculas, devuelve la existente."""
    name = clean_name(name)
    existing = db.scalar(select(Tag).where(Tag.space_id == space_id, Tag.key == name.casefold()))
    if existing is not None:
        return existing
    if (db.scalar(select(func.count()).select_from(Tag).where(Tag.space_id == space_id)) or 0) >= MAX_TAGS:
        raise Invalid(f"Como mucho {MAX_TAGS} etiquetas por espacio", code="too_many_tags")
    tag = Tag(space_id=space_id, name=name, key=name.casefold(), created_by=user.id)
    db.add(tag)
    db.flush()
    audit.record(
        db,
        "tag.created",
        actor_id=user.id,
        space_id=space_id,
        target_type="tag",
        target_id=tag.id,
        request=request,
        detail={"name": tag.name},
    )
    return tag


def rename(db: Session, tag: Tag, user: User, name: str, request: RequestInfo) -> None:
    name = clean_name(name)
    if name == tag.name:
        return
    clash = db.scalar(
        select(Tag.id).where(Tag.space_id == tag.space_id, Tag.key == name.casefold(), Tag.id != tag.id)
    )
    if clash is not None:
        raise Conflict("Ya hay otra etiqueta con ese nombre", code="tag_exists")
    audit.record(
        db,
        "tag.renamed",
        actor_id=user.id,
        space_id=tag.space_id,
        target_type="tag",
        target_id=tag.id,
        request=request,
        detail={"from": tag.name, "to": name},
    )
    tag.name, tag.key = name, name.casefold()


def remove(db: Session, tag: Tag, user: User, request: RequestInfo) -> None:
    audit.record(
        db,
        "tag.deleted",
        actor_id=user.id,
        space_id=tag.space_id,
        target_type="tag",
        target_id=tag.id,
        request=request,
        detail={"name": tag.name},
    )
    db.delete(tag)  # asset_tags se borra en cascada; los elementos no se tocan


def membership(db: Session, tag_id: uuid.UUID, ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    query = select(AssetTag.asset_id).where(AssetTag.tag_id == tag_id, AssetTag.asset_id.in_(list(ids)))
    return set(db.scalars(query))


def add_assets(db: Session, tag: Tag, ids: list[uuid.UUID], user_id: uuid.UUID | None) -> int:
    """Pone la etiqueta (solo a elementos del mismo espacio; si ya la tenían, no cuenta)."""
    valid = list(db.scalars(select(Asset.id).where(Asset.space_id == tag.space_id, Asset.id.in_(ids))))
    if not valid:
        return 0
    result = db.execute(
        insert(AssetTag)
        .values([{"tag_id": tag.id, "asset_id": i, "added_by": user_id} for i in valid])
        .on_conflict_do_nothing()
        .returning(AssetTag.asset_id)
    )
    return len(result.all())


def remove_assets(db: Session, tag: Tag, ids: list[uuid.UUID]) -> int:
    result = db.execute(delete(AssetTag).where(AssetTag.tag_id == tag.id, AssetTag.asset_id.in_(ids)))
    return int(result.rowcount)  # type: ignore[attr-defined]


def tag_ids_by_asset(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Etiquetas de cada elemento de una página (una sola consulta)."""
    ids = list(ids)
    out: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    if not ids:
        return out
    rows = db.execute(
        select(AssetTag.asset_id, AssetTag.tag_id)
        .join(Tag, Tag.id == AssetTag.tag_id)
        .where(AssetTag.asset_id.in_(ids))
        .order_by(Tag.key)
    ).all()
    for asset_id, tag_id in rows:
        out[asset_id].append(tag_id)
    return out


def tags_of(db: Session, asset_id: uuid.UUID) -> list[dict[str, str]]:
    rows = db.execute(
        select(Tag.id, Tag.name)
        .join(AssetTag, AssetTag.tag_id == Tag.id)
        .where(AssetTag.asset_id == asset_id)
        .order_by(Tag.key)
    ).all()
    return [{"id": str(i), "name": n} for i, n in rows]


def tag_names_by_asset(db: Session, space_id: uuid.UUID) -> dict[Any, list[str]]:
    """Para exportar: nombres de etiqueta de cada elemento del espacio."""
    result: dict[Any, list[str]] = defaultdict(list)
    rows = db.execute(
        select(AssetTag.asset_id, Tag.name)
        .join(Tag, Tag.id == AssetTag.tag_id)
        .where(Tag.space_id == space_id)
        .order_by(Tag.key)
    ).all()
    for asset_id, name in rows:
        result[asset_id].append(name)
    return result
