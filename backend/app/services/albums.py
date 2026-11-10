"""Álbumes. Por ahora, solo el filtro que usa la línea temporal."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Select

AnySelect = Select[*tuple[Any, ...]]

if TYPE_CHECKING:
    from app.services.assets import Filters


def apply_album_filter(stmt: AnySelect, f: Filters) -> AnySelect:
    return stmt


def add_on_upload(db: object, space_id: object, album_id: object, asset_id: object) -> None:
    """Añade al álbum elegido al subir. Por completar."""


def albums_of(db: object, asset_id: object) -> list[dict[str, str]]:
    """Álbumes en los que está un elemento. Por completar."""
    return []


def album_names_by_asset(db: object, space_id: object) -> dict[object, list[str]]:
    """Nombres de los álbumes de cada elemento del espacio (manifiestos). Por completar."""
    return {}
