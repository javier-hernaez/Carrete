"""Mapa del espacio: fotos con GPS agrupadas por zonas. Solo coordenadas de este espacio."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import DB, FullAuth
from app.services import geo, spaces

router = APIRouter(prefix="/api/v1", tags=["mapa"])


class Cluster(BaseModel):
    count: int
    lat: float
    lon: float
    bounds: list[float]
    cover_id: str


@router.get("/spaces/{space_id}/map", response_model=list[Cluster])
def space_map(
    space_id: uuid.UUID,
    current: FullAuth,
    db: DB,
    zoom: Annotated[float, Query(ge=0, le=22)] = 2,
    south: Annotated[float | None, Query(ge=-90, le=90)] = None,
    west: Annotated[float | None, Query(ge=-180, le=180)] = None,
    north: Annotated[float | None, Query(ge=-90, le=90)] = None,
    east: Annotated[float | None, Query(ge=-180, le=180)] = None,
) -> list[Cluster]:
    spaces.access(db, current.user, space_id)
    bounds = (south, west, north, east) if None not in (south, west, north, east) else None
    return [Cluster(**c) for c in geo.clusters(db, space_id, zoom=zoom, bounds=bounds)]  # type: ignore[arg-type]
