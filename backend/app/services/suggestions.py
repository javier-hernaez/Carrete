"""Sugerencias de álbum: agrupa la bandeja de entrada por días o escapadas y propone
«¿Crear álbum con estas 86 fotos del 12–15 de agosto?».

Un grupo se corta cuando entre dos fotos seguidas pasan más de 18 horas o hay más de 80 km.
Solo se proponen grupos de al menos 8 elementos que aún no estén en ningún álbum.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AlbumAsset, Asset
from app.media.places import distance_km

MAX_GAP = timedelta(hours=18)
MAX_JUMP_KM = 80.0
MIN_SIZE = 8
MAX_SUGGESTIONS = 20


@dataclass
class Suggestion:
    start: datetime
    end: datetime
    ids: list[uuid.UUID] = field(default_factory=list)
    places: Counter[str] = field(default_factory=Counter)

    @property
    def place(self) -> str | None:
        common = self.places.most_common(1)
        return common[0][0] if common else None


def suggest(db: Session, space_id: uuid.UUID) -> list[Suggestion]:
    rows = db.execute(
        select(Asset.id, Asset.taken_at_local, Asset.lat, Asset.lon, Asset.place_name)
        .where(
            Asset.space_id == space_id,
            Asset.review_state == "pending",
            Asset.trashed_at.is_(None),
            Asset.id.not_in(select(AlbumAsset.asset_id)),
        )
        .order_by(Asset.taken_at_local, Asset.id)
    ).all()
    groups: list[Suggestion] = []
    current: Suggestion | None = None
    last_point: tuple[float, float] | None = None
    for asset_id, taken, lat, lon, place in rows:
        point = (lat, lon) if lat is not None and lon is not None else None
        jump = point is not None and last_point is not None and distance_km(*last_point, *point) > MAX_JUMP_KM
        if current is None or taken - current.end > MAX_GAP or jump:
            current = Suggestion(taken, taken)
            groups.append(current)
        current.end = taken
        current.ids.append(asset_id)
        if place:
            current.places[place] += 1
        if point is not None:
            last_point = point
    big = [g for g in groups if len(g.ids) >= MIN_SIZE]
    return sorted(big, key=lambda g: g.end, reverse=True)[:MAX_SUGGESTIONS]
