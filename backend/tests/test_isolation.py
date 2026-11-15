"""Aislamiento entre espacios: quien no es miembro no ve nada de un espacio, ni entrando por la
ruta del espacio ni pidiendo directamente el id de una foto, un álbum o una exportación, ni colando ids
ajenos en peticiones sobre un espacio propio. El administrador, en cambio, entra en todo."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import Engine

from app.jobs.worker import Worker
from tests.helpers import Person, invite, join
from tests.media_files import make_jpeg
from tests.test_uploads import drain, tus_create, upload

ZERO = str(uuid.UUID(int=0))


def test_outsider_sees_nothing_of_a_foreign_space(  # type: ignore[no-untyped-def]
    owner: Person, worker: Worker, tmp_path: Path, engine: Engine, new_client
) -> None:
    javier = owner  # administrador, dueño de «Pareja»
    pareja = javier.spaces["Pareja"]
    lucia = join(new_client(), engine, invite(javier, pareja), "lucia")
    pedro = join(new_client(), engine, invite(javier, pareja), "pedro")  # colaborador en «Pareja»
    familia = lucia.post("/api/v1/spaces", json={"name": "Familia"}).json()["id"]
    foto = upload(lucia, familia, make_jpeg(tmp_path / "secreta.jpg", pattern=3))
    drain(worker)
    album = lucia.post(
        f"/api/v1/spaces/{familia}/albums",
        json={"name": "Vacaciones secretas", "description": "Solo la familia", "asset_ids": [foto]},
    ).json()["id"]
    lucia.patch(f"/api/v1/spaces/{familia}/albums/{album}", json={"name": "Boda secreta"})
    export = lucia.post(f"/api/v1/spaces/{familia}/exports", json={"ids": [foto]})
    assert export.status_code == 201, export.text
    export_id = export.json()["id"]
    assert lucia.get(f"/api/v1/assets/{foto}").status_code == 200

    assert familia not in {s["id"] for s in pedro.get("/api/v1/spaces").json()}
    assert familia not in {s["id"] for s in pedro.get("/api/v1/me").json()["spaces"]}

    s = f"/api/v1/spaces/{familia}"
    attempts: list[tuple[str, str, object]] = [
        ("get", f"/api/v1/assets/{foto}", None),
        ("get", f"/api/v1/assets/{foto}/thumb", None),
        ("get", f"/api/v1/assets/{foto}/preview", None),
        ("get", f"/api/v1/assets/{foto}/video", None),
        ("get", f"/api/v1/assets/{foto}/original", None),
        ("patch", f"/api/v1/assets/{foto}", {"description": "mía"}),
        ("get", f"{s}/assets", None),
        ("get", f"{s}/timeline", None),
        ("get", f"{s}/counters", None),
        ("get", f"{s}/trash", None),
        ("post", f"{s}/trash/empty", {"confirm_name": "Familia"}),
        ("post", f"{s}/assets/check", {"sha256": ["0" * 64]}),
        ("post", f"{s}/assets/batch", {"ids": [foto], "action": "trash"}),
        ("get", f"{s}/albums", None),
        ("post", f"{s}/albums", {"name": "Intrusa"}),
        ("get", f"{s}/albums/{album}", None),
        ("patch", f"{s}/albums/{album}", {"name": "Mía"}),
        ("delete", f"{s}/albums/{album}", None),
        ("post", f"{s}/albums/{album}/reorder", {"asset_id": foto}),
        ("get", f"{s}/suggestions", None),
        ("get", f"{s}/duplicates", None),
        ("post", f"{s}/duplicates/{ZERO}/resolve", {"keep": [foto]}),
        ("post", f"{s}/duplicates/{ZERO}/dismiss", None),
        ("post", f"{s}/duplicates/resolve-obvious", None),
        ("get", f"{s}/activity", None),
        ("get", f"{s}/map", None),
        ("get", f"{s}/exports", None),
        ("post", f"{s}/exports", {"ids": [foto]}),
        ("get", f"{s}/exports/{export_id}", None),
        ("get", f"{s}/exports/{export_id}/files/1", None),
        ("delete", f"{s}/exports/{export_id}", None),
        ("get", f"{s}/imports", None),
    ]
    for method, url, body in attempts:
        kwargs = {"json": body} if body is not None else {}
        response = getattr(pedro, method)(url, **kwargs)
        assert response.status_code == 404, (method, url, response.status_code, response.text)
        for secret in ("Familia", "Vacaciones", "Boda", "secreta"):
            assert secret not in response.text, (method, url)

    # Subir a un espacio ajeno tampoco se puede
    assert tus_create(pedro, familia, make_jpeg(tmp_path / "intrusa.jpg", pattern=4)).status_code == 404

    # Ids ajenos colados en peticiones sobre un espacio propio: 404 o se ignoran
    p = f"/api/v1/spaces/{pareja}"
    assert pedro.get(f"{p}/albums/{album}").status_code == 404
    assert pedro.get(f"{p}/exports/{export_id}").status_code == 404
    assert pedro.get(f"{p}/exports/{export_id}/files/1").status_code == 404
    assert pedro.post(f"{p}/exports", json={"album_ids": [album]}).status_code == 404
    propia = upload(pedro, pareja, make_jpeg(tmp_path / "propia.jpg", pattern=6))
    for action in ("add_album", "remove_album"):
        batch = {"ids": [propia], "action": action, "album_id": album}
        assert pedro.post(f"{p}/assets/batch", json=batch).status_code == 404
    mine = pedro.post(f"{p}/albums", json={"name": "Nuestro", "asset_ids": [foto]}).json()
    assert mine["count"] == 0
    assert pedro.patch(f"{p}/albums/{mine['id']}", json={"cover_asset_id": foto}).status_code == 422
    favorite = {"ids": [foto], "action": "favorite", "value": True}
    assert pedro.post(f"{p}/assets/batch", json=favorite).json()["count"] == 0
    assert pedro.post(f"{p}/assets/check", json={"sha256": ["0" * 64]}).status_code == 200

    # Lucía sigue teniendo todo intacto
    assert lucia.get(f"/api/v1/assets/{foto}").json()["trashed_at"] is None
    assert lucia.get(f"{s}/albums/{album}").json()["count"] == 1


def test_admin_sees_and_manages_every_space(  # type: ignore[no-untyped-def]
    owner: Person, worker: Worker, tmp_path: Path, engine: Engine, new_client
) -> None:
    """El administrador tiene acceso de propietario a todos los espacios, aunque no sea miembro."""
    javier = owner
    lucia = join(new_client(), engine, invite(javier, javier.spaces["Pareja"]), "lucia")
    familia = lucia.post("/api/v1/spaces", json={"name": "Familia"}).json()["id"]
    foto = upload(lucia, familia, make_jpeg(tmp_path / "suya.jpg", pattern=7))
    drain(worker)
    album = lucia.post(f"/api/v1/spaces/{familia}/albums", json={"name": "Vacaciones", "asset_ids": [foto]})
    album_id = album.json()["id"]

    s = f"/api/v1/spaces/{familia}"
    assert [a["id"] for a in javier.get(f"{s}/assets").json()["items"]] == [foto]
    assert javier.get(f"/api/v1/assets/{foto}").json()["space_id"] == familia
    for kind in ("thumb", "preview", "original"):
        assert javier.get(f"/api/v1/assets/{foto}/{kind}").status_code == 200, kind
    assert javier.get(f"{s}/albums/{album_id}").json()["name"] == "Vacaciones"
    assert javier.patch(f"/api/v1/assets/{foto}", json={"description": "Revisada"}).status_code == 204
    assert (
        javier.post(f"{s}/assets/batch", json={"ids": [foto], "action": "favorite", "value": True}).json()[
            "count"
        ]
        == 1
    )
    # Subir también
    assert upload(javier, familia, make_jpeg(tmp_path / "del-admin.jpg", pattern=8))

    # Y la auditoría muestra el detalle completo
    items = javier.get("/api/v1/admin/audit", params={"limit": 500}).json()["items"]
    created = next(i for i in items if i["action"] == "album.created" and i["space_id"] == familia)
    assert created["detail"]["name"] == "Vacaciones"
