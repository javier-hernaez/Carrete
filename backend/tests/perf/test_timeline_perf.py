"""Rendimiento de la línea temporal con 50 000 elementos.

Guion reproducible; no se ejecuta en cada prueba porque tarda. Para lanzarlo:
    CARRETE_PERF=1 make backend-test   (o pytest tests/perf -s)
Crea 50 000 elementos sintéticos directamente en PostgreSQL (sin ficheros) y mide lo que pide la web.
"""

from __future__ import annotations

import os
import statistics
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.helpers import Person

pytestmark = pytest.mark.skipif(os.environ.get("CARRETE_PERF") != "1", reason="Solo con CARRETE_PERF=1")

N = 50_000


def _seed(engine: Engine, space_id: str, user_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO blobs (id, sha256, size_bytes, mime, ext, ref_count)
                SELECT gen_random_uuid(), md5(i::text) || md5((i * 7)::text), 3000000, 'image/jpeg', 'jpg', 1
                FROM generate_series(1, :n) AS i
                """
            ),
            {"n": N},
        )
        conn.execute(
            text(
                """
                INSERT INTO assets (id, space_id, blob_id, kind, original_filename, uploaded_by, taken_at_local,
                                    taken_at_source, width, height, review_state, processing_state, source, thumbhash)
                SELECT gen_random_uuid(), :space, b.id,
                       CASE WHEN random() < 0.05 THEN 'video' ELSE 'photo' END,
                       'IMG_' || row_number() OVER () || '.jpg', :user,
                       timestamp '2014-01-01' + (random() * interval '4000 days'), 'exif', 4000, 3000,
                       (ARRAY['pending', 'kept', 'kept', 'discarded'])[1 + floor(random() * 4)::int], 'ready', 'camera',
                       '1QcSHQRnh493V4dIh4eXh1h4kJUI'
                FROM blobs b
                """
            ),
            {"space": space_id, "user": user_id},
        )
        conn.execute(text("ANALYZE assets"))


def _timed(fn, runs: int = 7) -> float:  # type: ignore[no-untyped-def]
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)


def test_timeline_with_50000(owner: Person, engine: Engine) -> None:
    client: TestClient = owner.client
    space = owner.spaces["Pareja"]
    _seed(engine, space, owner.get("/api/v1/me").json()["id"])

    first = _timed(lambda: client.get(f"/api/v1/spaces/{space}/assets", params={"limit": 300}))
    page = client.get(f"/api/v1/spaces/{space}/assets", params={"limit": 300}).json()
    cursor = page["next_cursor"]
    deep = None
    for _ in range(40):  # avanzar 12 000 elementos
        cursor = client.get(f"/api/v1/spaces/{space}/assets", params={"limit": 300, "cursor": cursor}).json()[
            "next_cursor"
        ]
    deep = _timed(
        lambda: client.get(f"/api/v1/spaces/{space}/assets", params={"limit": 300, "cursor": cursor})
    )
    months = _timed(lambda: client.get(f"/api/v1/spaces/{space}/timeline"))
    jump = _timed(
        lambda: client.get(f"/api/v1/spaces/{space}/assets", params={"limit": 300, "start": "2016-06-30"})
    )
    pending = _timed(
        lambda: client.get(
            f"/api/v1/spaces/{space}/assets", params={"limit": 500, "review": "pending", "order": "asc"}
        )
    )
    counters = _timed(lambda: client.get(f"/api/v1/spaces/{space}/counters"))
    total = client.get(f"/api/v1/spaces/{space}/timeline").json()["total"]

    with engine.connect() as conn:
        plan = "\n".join(
            r[0]
            for r in conn.execute(
                text(
                    "EXPLAIN SELECT * FROM assets WHERE space_id = :s AND trashed_at IS NULL "
                    "AND review_state != 'discarded' ORDER BY taken_at_local DESC, id DESC LIMIT 301"
                ),
                {"s": space},
            )
        )
    results = {
        "primera página (300)": first,
        "página 41 con cursor": deep,
        "resumen por meses": months,
        "saltar a una fecha": jump,
        "bandeja de Revisar (500)": pending,
        "contadores": counters,
    }
    print(f"\nLínea temporal con {total} elementos visibles de {N} (mediana de 7, ms):")
    for name, value in results.items():
        print(f"  {name:28s} {value:7.1f}")
    print(plan)
    # Objetivo: primer contenido en < 1,5 s en el navegador. En el servidor, con margen:
    assert first < 300 and deep < 300 and jump < 400 and months < 600
