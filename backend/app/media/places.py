"""Nombre del lugar de una foto, calculado en el servidor con datos locales de GeoNames.

Nunca se consulta ningún servicio externo: las coordenadas no salen del mini PC. Se busca la ciudad de
más de 15 000 habitantes más cercana (cuadrícula de 1°), hasta 150 km.
"""

from __future__ import annotations

import gzip
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "places.tsv.gz"
MAX_KM = 150.0


@dataclass(frozen=True)
class Place:
    geonameid: int
    name: str
    region: str
    country: str
    lat: float
    lon: float


def _cell(lat: float, lon: float) -> tuple[int, int]:
    return math.floor(lat), math.floor(lon)


@lru_cache(maxsize=1)
def _index() -> dict[tuple[int, int], list[Place]]:
    grid: dict[tuple[int, int], list[Place]] = {}
    with gzip.open(DATA, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            gid, name, region, country, lat, lon = line.rstrip("\n").split("\t")
            place = Place(int(gid), name, region, country, float(lat), float(lon))
            grid.setdefault(_cell(place.lat, place.lon), []).append(place)
    return grid


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def nearest(lat: float, lon: float) -> Place | None:
    grid = _index()
    best: tuple[float, Place] | None = None
    cy, cx = _cell(lat, lon)
    for radius in range(3):  # 1°, luego 3×3, luego 5×5 celdas (~150 km en latitudes medias)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dy), abs(dx)) != radius:
                    continue
                lon_cell = ((cx + dx + 180) % 360) - 180
                for place in grid.get((cy + dy, lon_cell), []):
                    d = distance_km(lat, lon, place.lat, place.lon)
                    if best is None or d < best[0]:
                        best = (d, place)
        if best is not None and best[0] <= 111 * radius:
            break
    if best is None or best[0] > MAX_KM:
        return None
    return best[1]
