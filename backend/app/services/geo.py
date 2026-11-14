"""Ubicación: agregados para el mapa y asignación del lugar."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session

from app.db.models import Asset
from app.media.places import nearest


def assign_place(asset: Asset) -> None:
    if asset.lat is None or asset.lon is None:
        asset.place_id = asset.place_name = asset.place_region = asset.place_country = None
        return
    place = nearest(asset.lat, asset.lon)
    if place is None:
        # 0 = buscado y lejos de cualquier ciudad: el relleno no vuelve a intentarlo.
        asset.place_id = 0
        asset.place_name = asset.place_region = asset.place_country = None
        return
    asset.place_id, asset.place_name = place.geonameid, place.name
    asset.place_region, asset.place_country = place.region or None, place.country


def backfill_places(db: Session, limit: int = 5000) -> int:
    """Pone el lugar a las fotos con GPS que aún no lo tienen (las procesadas antes de tener mapa)."""
    pending = db.scalars(
        select(Asset)
        .where(Asset.lat.is_not(None), Asset.lon.is_not(None), Asset.place_id.is_(None))
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    for asset in pending:
        assign_place(asset)
    return len(pending)


def cell_size(zoom: float) -> float:
    """Tamaño de la celda de agrupación en grados: ~1/6 del ancho de una tesela del nivel de zoom."""
    return 360.0 / (2 ** max(0.0, min(zoom, 20.0))) / 6


def clusters(
    db: Session, space_id: uuid.UUID, *, zoom: float, bounds: tuple[float, float, float, float] | None
) -> list[dict[str, Any]]:
    size = cell_size(zoom)
    gy = func.floor(Asset.lat / size)
    gx = func.floor(Asset.lon / size)
    query = select(
        func.count().label("count"),
        func.avg(Asset.lat).label("lat"),
        func.avg(Asset.lon).label("lon"),
        func.min(Asset.lat),
        func.min(Asset.lon),
        func.max(Asset.lat),
        func.max(Asset.lon),
        func.array_agg(aggregate_order_by(Asset.id, Asset.taken_at_local.desc())).label("ids"),
    ).where(
        Asset.space_id == space_id,
        Asset.lat.is_not(None),
        Asset.trashed_at.is_(None),
        Asset.review_state != "discarded",
    )
    if bounds is not None:
        south, west, north, east = bounds
        query = query.where(Asset.lat.between(south, north))
        query = query.where(
            Asset.lon.between(west, east) if west <= east else (Asset.lon >= west) | (Asset.lon <= east)
        )
    rows = db.execute(query.group_by(gy, gx).order_by(func.count().desc()).limit(2000)).all()
    return [
        {
            "count": int(count),
            "lat": float(lat),
            "lon": float(lon),
            "bounds": [float(s), float(w), float(n), float(e)],
            "cover_id": str(ids[0]),
        }
        for count, lat, lon, s, w, n, e, ids in rows
    ]
