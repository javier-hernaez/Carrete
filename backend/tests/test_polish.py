"""Lugares, mapa, ubicación manual, búsqueda, sugerencias de álbum y llaves de acceso."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.media.places import distance_km, nearest
from app.services.geo import cell_size
from tests.helpers import Person, invite, join, setup_admin, totp_code
from tests.media_files import make_jpeg
from tests.softkey import SoftKey
from tests.test_uploads import drain, upload


@pytest.mark.parametrize(
    ("lat", "lon", "name", "country"),
    [
        (43.3614, -5.8494, "Oviedo", "ES"),
        (40.4168, -3.7038, "Madrid", "ES"),
        (35.6762, 139.6503, "Tokyo", "JP"),
        (-33.8688, 151.2093, "Sydney", "AU"),
    ],
)
def test_reverse_geocoding_is_local(lat: float, lon: float, name: str, country: str) -> None:
    place = nearest(lat, lon)
    # En las grandes ciudades, lo más cercano puede ser un barrio: entonces la ciudad es la región.
    assert place is not None and place.country == country and (name in place.name or name in place.region)


def test_no_place_in_the_middle_of_the_ocean() -> None:
    assert nearest(0.0, -30.0) is None
    assert round(distance_km(40.4168, -3.7038, 41.3874, 2.1686)) == 505
    assert cell_size(0) > cell_size(10)


def test_map_location_and_search(owner: Person, worker, tmp_path: Path, engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    space = owner.spaces["Pareja"]
    oviedo = upload(
        owner, space, make_jpeg(tmp_path / "oviedo.jpg", gps=(43.3614, -5.8494), color=(200, 20, 20))
    )
    gijon = upload(
        owner, space, make_jpeg(tmp_path / "gijon.jpg", gps=(43.5357, -5.6615), color=(20, 200, 20))
    )
    tokyo = upload(
        owner, space, make_jpeg(tmp_path / "tokio.jpg", gps=(35.6762, 139.6503), color=(20, 20, 200))
    )
    nowhere = upload(owner, space, make_jpeg(tmp_path / "sin.jpg", color=(120, 120, 20)))
    drain(worker)
    detail = owner.get(f"/api/v1/assets/{oviedo}").json()
    assert (detail["place_name"], detail["place_region"], detail["place_country"]) == (
        "Oviedo",
        "Asturias",
        "ES",
    )

    world = owner.get(f"/api/v1/spaces/{space}/map", params={"zoom": 1}).json()
    assert sorted(c["count"] for c in world) == [1, 2]
    asturias = owner.get(
        f"/api/v1/spaces/{space}/map", params={"zoom": 1, "south": 40, "west": -10, "north": 45, "east": 0}
    ).json()
    assert len(asturias) == 1 and asturias[0]["count"] == 2 and asturias[0]["cover_id"] in {oviedo, gijon}
    zoomed = owner.get(f"/api/v1/spaces/{space}/map", params={"zoom": 12}).json()
    assert len(zoomed) == 3

    s, w, n, e = asturias[0]["bounds"]
    inside = owner.get(
        f"/api/v1/spaces/{space}/assets", params={"south": s, "west": w, "north": n, "east": e}
    ).json()["items"]
    assert {a["id"] for a in inside} == {oviedo, gijon}
    unlocated = owner.get(f"/api/v1/spaces/{space}/assets", params={"located": "false"}).json()["items"]
    assert [a["id"] for a in unlocated] == [nowhere]

    # Ubicación a mano y deshacer
    moved = owner.post(
        f"/api/v1/spaces/{space}/assets/batch",
        json={"ids": [nowhere], "action": "set_location", "lat": 40.4168, "lon": -3.7038},
    ).json()
    assert owner.get(f"/api/v1/assets/{nowhere}").json()["place_name"] == "Madrid"
    owner.post(f"/api/v1/spaces/{space}/assets/batch", json={"ids": [nowhere], **moved["undo"]})
    assert owner.get(f"/api/v1/assets/{nowhere}").json()["lat"] is None
    assert (
        owner.post(
            f"/api/v1/spaces/{space}/assets/batch",
            json={"ids": [nowhere], "action": "set_location", "lat": 40.0},
        ).status_code
        == 422
    )

    # Búsqueda por lugar y por álbum
    found = owner.get(f"/api/v1/spaces/{space}/assets", params={"q": "astur"}).json()["items"]
    assert {a["id"] for a in found} == {oviedo, gijon}
    owner.post(f"/api/v1/spaces/{space}/albums", json={"name": "Japón 2024", "asset_ids": [tokyo]})
    assert [
        a["id"] for a in owner.get(f"/api/v1/spaces/{space}/assets", params={"q": "japón"}).json()["items"]
    ] == [tokyo]

    # Aislamiento: otro espacio no ve estas coordenadas
    ajena = join(new_client(), engine, invite(owner, space, "viewer"), "ajena")
    otro = ajena.post("/api/v1/spaces", json={"name": "Suyo"}).json()["id"]
    assert ajena.get(f"/api/v1/spaces/{otro}/map").json() == []
    owner.delete(f"/api/v1/spaces/{space}/members/{ajena.get('/api/v1/me').json()['id']}")
    assert ajena.get(f"/api/v1/spaces/{space}/map").status_code == 404


def test_album_suggestions(owner: Person, tmp_path: Path, engine: Engine) -> None:
    space = owner.spaces["Pareja"]
    trip = [
        upload(owner, space, make_jpeg(tmp_path / f"v{i}.jpg", color=(i * 20, 60, 200 - i * 20)))
        for i in range(9)
    ]
    other = [
        upload(owner, space, make_jpeg(tmp_path / f"o{i}.jpg", color=(i * 25, 200, 60))) for i in range(3)
    ]
    with engine.begin() as conn:
        for n, asset in enumerate(trip):  # una escapada de dos días en agosto
            when = f"2025-08-12 {15 + n}:00:00" if n < 5 else f"2025-08-13 0{n + 1}:00:00"
            conn.execute(
                text("UPDATE assets SET taken_at_local = :t, place_name = 'Oviedo' WHERE id = :i"),
                {"t": when, "i": asset},
            )
        for n, asset in enumerate(other):
            conn.execute(
                text("UPDATE assets SET taken_at_local = :t WHERE id = :i"),
                {"t": f"2025-09-0{n + 1} 10:00:00", "i": asset},
            )
    suggestions = owner.get(f"/api/v1/spaces/{space}/suggestions").json()
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s["count"] == 9 and s["place"] == "Oviedo" and set(s["asset_ids"]) == set(trip)
    assert s["start"].startswith("2025-08-12") and s["end"].startswith("2025-08-13")
    # Al crear el álbum, la sugerencia desaparece
    owner.post(f"/api/v1/spaces/{space}/albums", json={"name": "Oviedo 2025", "asset_ids": s["asset_ids"]})
    assert owner.get(f"/api/v1/spaces/{space}/suggestions").json() == []


def test_passkeys(client: TestClient, engine: Engine, settings) -> None:  # type: ignore[no-untyped-def]
    admin = setup_admin(client, engine)
    key = SoftKey("carrete.example.ts.net", settings.public_origin)
    options = admin.post("/api/v1/auth/passkeys/register/options").json()
    assert options["options"]["rp"]["id"] == "carrete.example.ts.net"
    assert options["options"]["authenticatorSelection"]["userVerification"] == "required"
    created = admin.post(
        "/api/v1/auth/passkeys",
        json={
            "challenge_id": options["challenge_id"],
            "credential": key.create(options["options"]),
            "name": "Portátil",
        },
    )
    assert created.status_code == 201, created.text
    # El reto es de un solo uso
    again = admin.post(
        "/api/v1/auth/passkeys",
        json={"challenge_id": options["challenge_id"], "credential": key.create(options["options"])},
    )
    assert again.json()["code"] == "challenge_expired"
    assert [p["name"] for p in admin.get("/api/v1/auth/passkeys").json()] == ["Portátil"]

    # Entrar sin contraseña ni código
    anon = TestClient(
        client.app,
        base_url=settings.public_url,
        headers={"Origin": settings.public_origin, "X-Carrete-Request": "1"},
    )
    login = anon.post("/api/v1/auth/passkeys/login/options").json()
    response = anon.post(
        "/api/v1/auth/passkeys/login",
        json={"challenge_id": login["challenge_id"], "credential": key.get(login["options"])},
    )
    assert response.json() == {"stage": "full"} and response.headers["set-cookie"].startswith(
        "__Host-carrete="
    )
    assert anon.get("/api/v1/me").json()["username"] == "javier"

    # Origen equivocado (otra app del mismo equipo, otro puerto) o sin verificación del usuario: no
    for kwargs in ({"origin": "https://carrete.example.ts.net:8443"}, {"user_verified": False}):
        bad_opts = anon.post("/api/v1/auth/passkeys/login/options").json()
        bad = anon.post(
            "/api/v1/auth/passkeys/login",
            json={
                "challenge_id": bad_opts["challenge_id"],
                "credential": key.get(bad_opts["options"], **kwargs),
            },
        )
        assert bad.status_code == 401
    unknown = SoftKey("carrete.example.ts.net", settings.public_origin)
    unknown.user_handle = b"x"
    opts = anon.post("/api/v1/auth/passkeys/login/options").json()
    assert (
        anon.post(
            "/api/v1/auth/passkeys/login",
            json={"challenge_id": opts["challenge_id"], "credential": unknown.get(opts["options"])},
        ).status_code
        == 401
    )

    # Borrar la llave exige reautenticación reciente
    passkey_id = admin.get("/api/v1/auth/passkeys").json()[0]["id"]
    with engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET reauth_at = now() - interval '1 hour'"))
    assert admin.delete(f"/api/v1/auth/passkeys/{passkey_id}").json()["code"] == "reauth_required"
    code = totp_code(admin.totp_secret or "", engine, "javier")
    admin.post("/api/v1/auth/reauth", json={"password": "una frase larga y segura", "code": code})
    assert admin.delete(f"/api/v1/auth/passkeys/{passkey_id}").status_code == 204
    opts = anon.post("/api/v1/auth/passkeys/login/options").json()
    assert (
        anon.post(
            "/api/v1/auth/passkeys/login",
            json={"challenge_id": opts["challenge_id"], "credential": key.get(opts["options"])},
        ).status_code
        == 401
    )


def test_places_backfill_for_older_photos(owner: Person, worker, tmp_path: Path, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy.orm import Session

    from app.jobs import schedule
    from app.services.geo import backfill_places

    space = owner.spaces["Pareja"]
    seville = upload(owner, space, make_jpeg(tmp_path / "s.jpg", gps=(37.3886, -5.9823), color=(9, 9, 9)))
    ocean = upload(owner, space, make_jpeg(tmp_path / "o.jpg", gps=(30.0, -40.0), color=(90, 9, 9)))
    drain(worker)
    with engine.begin() as conn:  # como si se hubieran procesado antes de tener mapa
        conn.execute(text("UPDATE assets SET place_id = NULL, place_name = NULL, place_country = NULL"))
    assert "backfill_places" in schedule.PERIODIC
    with Session(engine) as db:
        assert backfill_places(db) == 2
        db.commit()
        assert backfill_places(db) == 0  # la del océano queda marcada con 0 y no se repite
    assert owner.get(f"/api/v1/assets/{seville}").json()["place_name"] == "Sevilla"
    assert owner.get(f"/api/v1/assets/{ocean}").json()["place_name"] is None
