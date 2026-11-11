"""Revisar, favoritas, álbumes, fechas, repetidas, contadores y actividad."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.jobs.worker import Worker
from tests.helpers import Person, invite, join
from tests.media_files import make_jpeg, sha256
from tests.test_uploads import TUS, drain, tus_patch, upload


def batch(person: Person, space: str, ids: list[str], action: str, **params: object):  # type: ignore[no-untyped-def]
    return person.post(f"/api/v1/spaces/{space}/assets/batch", json={"ids": ids, "action": action, **params})


def states(person: Person, space: str) -> dict[str, str]:
    items = person.get(
        f"/api/v1/spaces/{space}/assets", params={"review": ["pending", "kept", "discarded"]}
    ).json()["items"]
    return {a["id"]: a["review_state"] for a in items}


@pytest.fixture
def three(owner: Person, tmp_path: Path) -> list[str]:
    space = owner.spaces["Pareja"]
    return [
        upload(owner, space, make_jpeg(tmp_path / f"{i}.jpg", pattern=i, color=(40 * i, 90, 140)))
        for i in range(3)
    ]


def test_review_with_per_item_undo(owner: Person, three: list[str], engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    space = owner.spaces["Pareja"]
    a, b, c = three
    assert batch(owner, space, [a], "review", state="kept").json()["count"] == 1
    assert batch(owner, space, [b], "review", state="discarded").json()["count"] == 1
    # Acción masiva sobre estados distintos… y deshacer devuelve a cada uno el suyo
    response = batch(owner, space, [a, b, c], "review", state="kept").json()
    assert response["count"] == 2
    assert states(owner, space) == {a: "kept", b: "kept", c: "kept"}
    undo = response["undo"]
    assert batch(owner, space, [a, b, c], **undo).json()["count"] == 3
    assert states(owner, space) == {a: "kept", b: "discarded", c: "pending"}
    # Lo descartado no aparece por defecto
    visible = [x["id"] for x in owner.get(f"/api/v1/spaces/{space}/assets").json()["items"]]
    assert b not in visible and a in visible
    assert owner.get(f"/api/v1/spaces/{space}/counters").json() == {
        "pending_review": 1,
        "duplicates": 0,
        "discarded": 1,
        "trash": 0,
    }

    lector = join(new_client(), engine, invite(owner, space, "viewer"), "lector")
    assert batch(lector, space, [a], "review", state="pending").status_code == 403
    assert batch(owner, space, [a], "review", state="regular").status_code == 422
    # Una instantánea manipulada no puede tocar campos fuera de la lista
    hack = batch(
        owner, space, [a], "revert", snapshot={a: {"space_id": "otro"}, b: {"review_state": "inventado"}}
    )
    assert hack.json()["count"] == 0


def test_favorites(owner: Person, three: list[str]) -> None:
    space = owner.spaces["Pareja"]
    response = batch(owner, space, three[:2], "favorite", value=True).json()
    favs = owner.get(f"/api/v1/spaces/{space}/assets", params={"favorite": "true"}).json()["items"]
    assert {x["id"] for x in favs} == set(three[:2])
    batch(owner, space, three[:2], **response["undo"])
    assert owner.get(f"/api/v1/spaces/{space}/assets", params={"favorite": "true"}).json()["items"] == []


def test_albums(owner: Person, three: list[str], worker: Worker, tmp_path: Path) -> None:
    space = owner.spaces["Pareja"]
    drain(worker)
    a, b, c = three
    album = owner.post(
        f"/api/v1/spaces/{space}/albums", json={"name": "  Asturias   2025 ", "asset_ids": [a]}
    ).json()
    assert album["name"] == "Asturias 2025" and album["count"] == 1 and album["cover_asset_id"] == a

    added = batch(owner, space, [a, b], "add_album", album_id=album["id"]).json()
    assert added["count"] == 1
    in_album = owner.get(f"/api/v1/spaces/{space}/assets", params={"album_id": album["id"]}).json()["items"]
    assert {x["id"] for x in in_album} == {a, b}
    no_album = owner.get(f"/api/v1/spaces/{space}/assets", params={"no_album": "true"}).json()["items"]
    assert [x["id"] for x in no_album] == [c]
    # Deshacer «añadir» solo quita lo que no estaba antes
    batch(owner, space, [a, b], **added["undo"])
    assert {
        x["id"]
        for x in owner.get(f"/api/v1/spaces/{space}/assets", params={"album_id": album["id"]}).json()["items"]
    } == {a}

    batch(owner, space, [b, c], "add_album", album_id=album["id"])
    detail = owner.get(f"/api/v1/assets/{b}").json()
    assert detail["albums"] == [{"id": album["id"], "name": "Asturias 2025"}]

    # Orden manual: mover c entre a y b
    url = f"/api/v1/spaces/{space}/albums/{album['id']}"
    assert (
        owner.post(f"{url}/reorder", json={"asset_id": c, "after_id": a, "before_id": b}).status_code == 204
    )
    ordered = owner.get(
        f"/api/v1/spaces/{space}/assets", params={"album_id": album["id"], "order": "album"}
    ).json()["items"]
    assert [x["id"] for x in ordered] == [a, c, b]
    assert owner.get(url).json()["sort_mode"] == "manual"
    for _ in range(40):  # muchos movimientos seguidos en el mismo hueco no rompen el orden
        owner.post(f"{url}/reorder", json={"asset_id": c, "after_id": a, "before_id": b})
        owner.post(f"{url}/reorder", json={"asset_id": b, "after_id": a, "before_id": c})
    final = [
        x["id"]
        for x in owner.get(
            f"/api/v1/spaces/{space}/assets", params={"album_id": album["id"], "order": "album"}
        ).json()["items"]
    ]
    assert final[0] == a and set(final) == {a, b, c}

    # Portada, nombre, descripción; la portada debe ser del álbum
    assert owner.patch(url, json={"cover_asset_id": c, "description": "Verano"}).json()["cover_asset_id"] == c
    outsider = upload(owner, space, make_jpeg(tmp_path / "fuera.jpg", pattern=9))
    assert owner.patch(url, json={"cover_asset_id": outsider}).json()["code"] == "invalid_cover"
    listing = owner.get(f"/api/v1/spaces/{space}/albums").json()
    assert listing[0]["count"] == 3 and listing[0]["description"] == "Verano"

    # Eliminar el álbum no elimina las fotos
    assert owner.delete(url).status_code == 204
    assert owner.get(f"/api/v1/assets/{a}").status_code == 200
    assert owner.get(f"/api/v1/spaces/{space}/albums").json() == []


def test_upload_directly_into_album(owner: Person, tmp_path: Path) -> None:
    space = owner.spaces["Pareja"]
    album = owner.post(f"/api/v1/spaces/{space}/albums", json={"name": "Boda"}).json()
    photo = make_jpeg(tmp_path / "boda.jpg")
    meta = ",".join(
        f"{k} {base64.b64encode(v.encode()).decode()}"
        for k, v in {
            "filename": "boda.jpg",
            "sha256": sha256(photo),
            "space_id": space,
            "album_id": album["id"],
        }.items()
    )
    location = owner.post(
        "/api/v1/uploads",
        headers={**TUS, "Upload-Length": str(photo.stat().st_size), "Upload-Metadata": meta},
    ).headers["location"]
    asset = tus_patch(owner, location, photo.read_bytes(), 0).headers["carrete-asset-id"]
    detail = owner.get(f"/api/v1/assets/{asset}").json()
    assert detail["albums"][0]["name"] == "Boda" and detail["review_state"] == "pending"


def test_albums_are_isolated(owner: Person, three: list[str]) -> None:
    pareja = owner.spaces["Pareja"]
    familia = owner.post("/api/v1/spaces", json={"name": "Familia"}).json()["id"]
    foreign = owner.post(f"/api/v1/spaces/{familia}/albums", json={"name": "Suyo"}).json()["id"]
    assert batch(owner, pareja, three[:1], "add_album", album_id=foreign).status_code == 404
    assert owner.get(f"/api/v1/spaces/{pareja}/albums/{foreign}").status_code == 404
    assert owner.patch(f"/api/v1/spaces/{pareja}/albums/{foreign}", json={"name": "x"}).status_code == 404


def test_dates_manual_and_respected_by_processing(
    owner: Person, three: list[str], worker: Worker, sessions: sessionmaker[Session]
) -> None:
    space = owner.spaces["Pareja"]
    a, b, _ = three
    first = batch(owner, space, [a], "set_date", taken_at="2019-07-20T21:15:00", offset_minutes=120).json()
    detail = owner.get(f"/api/v1/assets/{a}").json()
    assert (detail["taken_at"], detail["taken_at_offset"], detail["taken_at_source"]) == (
        "2019-07-20T21:15:00",
        120,
        "manual",
    )
    drain(worker)  # el procesado no pisa una fecha corregida a mano
    assert owner.get(f"/api/v1/assets/{a}").json()["taken_at"] == "2019-07-20T21:15:00"
    before_b = owner.get(f"/api/v1/assets/{b}").json()["taken_at"]
    shifted = batch(owner, space, [a, b], "shift_date", minutes=-60 * 24).json()
    assert owner.get(f"/api/v1/assets/{a}").json()["taken_at"] == "2019-07-19T21:15:00"
    batch(owner, space, [a, b], **shifted["undo"])
    assert owner.get(f"/api/v1/assets/{b}").json()["taken_at"] == before_b
    batch(owner, space, [a], **first["undo"])
    assert owner.get(f"/api/v1/assets/{a}").json()["taken_at_source"] != "manual"
    assert batch(owner, space, [a], "set_date", taken_at="ayer").status_code == 422
    assert batch(owner, space, [a], "shift_date", minutes=0).status_code == 422


def test_description(owner: Person, three: list[str], engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    a = three[0]
    assert owner.patch(f"/api/v1/assets/{a}", json={"description": "  En la playa  "}).status_code == 204
    assert owner.get(f"/api/v1/assets/{a}").json()["description"] == "En la playa"
    found = owner.get(f"/api/v1/spaces/{owner.spaces['Pareja']}/assets", params={"q": "playa"}).json()[
        "items"
    ]
    assert [x["id"] for x in found] == [a]
    lector = join(new_client(), engine, invite(owner, owner.spaces["Pareja"], "viewer"), "lector")
    assert lector.patch(f"/api/v1/assets/{a}", json={"description": "x"}).status_code == 403


def _similar_set(tmp_path: Path) -> tuple[Path, Path, Path]:
    import pyvips

    base = make_jpeg(
        tmp_path / "IMG_20230415_183012.jpg", size=(1600, 1200), exif_date="2023:04:15 18:30:12", pattern=0
    )
    whatsapp = tmp_path / "IMG-20230415-WA0001.jpg"
    pyvips.Image.thumbnail(str(base), 800).jpegsave(str(whatsapp), Q=40, strip=True)
    other = make_jpeg(tmp_path / "otra.jpg", size=(1600, 1200), color=(20, 200, 40), pattern=1)
    return base, whatsapp, other


def test_duplicates_detect_resolve_and_undo(owner: Person, worker: Worker, tmp_path: Path) -> None:
    space = owner.spaces["Pareja"]
    base, whatsapp, other = _similar_set(tmp_path)
    best = upload(owner, space, base, chunk=1 << 20)
    worse = upload(owner, space, whatsapp, chunk=1 << 20)
    upload(owner, space, other, chunk=1 << 20)
    album = owner.post(f"/api/v1/spaces/{space}/albums", json={"name": "Viaje", "asset_ids": [worse]}).json()[
        "id"
    ]
    batch(owner, space, [worse], "favorite", value=True)
    owner.patch(f"/api/v1/assets/{worse}", json={"description": "Atardecer"})
    drain(worker)

    groups = owner.get(f"/api/v1/spaces/{space}/duplicates").json()
    assert len(groups) == 1
    group = groups[0]
    assert [m["id"] for m in group["members"]] == [best, worse]
    assert group["members"][0]["best"] and group["members"][0]["has_exif_date"]
    assert group["members"][1]["source"] == "whatsapp"
    assert owner.get(f"/api/v1/spaces/{space}/counters").json()["duplicates"] == 1

    resolved = owner.post(
        f"/api/v1/spaces/{space}/duplicates/{group['id']}/resolve", json={"keep": [best]}
    ).json()
    assert resolved == {"trashed": [worse]}
    kept = owner.get(f"/api/v1/assets/{best}").json()
    assert kept["is_favorite"] and kept["description"] == "Atardecer"
    assert kept["albums"] == [{"id": album, "name": "Viaje"}]
    assert owner.get(f"/api/v1/spaces/{space}/duplicates").json() == []

    # Deshacer: recuperar la foto y volver a proponer el grupo
    batch(owner, space, resolved["trashed"], "restore")
    assert owner.post(f"/api/v1/spaces/{space}/duplicates/{group['id']}/reopen").status_code == 204
    assert len(owner.get(f"/api/v1/spaces/{space}/duplicates").json()) == 1
    assert (
        owner.post(
            f"/api/v1/spaces/{space}/duplicates/{group['id']}/resolve",
            json={"keep": ["00000000-0000-7000-8000-000000000000"]},
        ).status_code
        == 422
    )


def test_duplicates_dismiss_is_remembered(
    owner: Person, worker: Worker, tmp_path: Path, sessions: sessionmaker[Session]
) -> None:
    space = owner.spaces["Pareja"]
    base, whatsapp, _ = _similar_set(tmp_path)
    upload(owner, space, base, chunk=1 << 20)
    upload(owner, space, whatsapp, chunk=1 << 20)
    drain(worker)
    group = owner.get(f"/api/v1/spaces/{space}/duplicates").json()[0]
    assert owner.post(f"/api/v1/spaces/{space}/duplicates/{group['id']}/dismiss").status_code == 204
    # Reprocesar no las vuelve a proponer
    with sessions() as s:
        s.execute(
            text(
                "INSERT INTO jobs (id, kind, payload) SELECT gen_random_uuid(), 'process_asset', "
                "jsonb_build_object('asset_id', id::text) FROM assets"
            )
        )
        s.commit()
    drain(worker)
    assert owner.get(f"/api/v1/spaces/{space}/duplicates").json() == []


def test_resolve_obvious(owner: Person, worker: Worker, tmp_path: Path) -> None:
    import shutil

    space = owner.spaces["Pareja"]
    base, _, _ = _similar_set(tmp_path)
    # La misma imagen, recomprimida sin cambiar de tamaño: casi idéntica (distancia mínima)
    import pyvips

    copy = tmp_path / "copia.jpg"
    pyvips.Image.new_from_file(str(base)).jpegsave(str(copy), Q=50, strip=True)
    keep = upload(owner, space, base, chunk=1 << 20)
    lose = upload(owner, space, copy, chunk=1 << 20)
    drain(worker)
    preview = owner.post(f"/api/v1/spaces/{space}/duplicates/resolve-obvious").json()
    assert preview == {"groups": 1, "keep": 1, "trash": 1, "trashed": [], "group_ids": []}
    applied = owner.post(
        f"/api/v1/spaces/{space}/duplicates/resolve-obvious", params={"apply": "true"}
    ).json()
    assert applied["trashed"] == [lose]
    assert owner.get(f"/api/v1/assets/{keep}").json()["trashed_at"] is None
    assert shutil is not None


def test_activity(owner: Person, three: list[str], engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    space = owner.spaces["Pareja"]
    owner.post(f"/api/v1/spaces/{space}/uploads/summary", json={"uploaded": 3, "duplicates": 0, "failed": 0})
    owner.post(f"/api/v1/spaces/{space}/albums", json={"name": "Asturias 2025"})
    lucia = join(new_client(), engine, invite(owner, space, "collaborator"), "lucia")
    items = lucia.get(f"/api/v1/spaces/{space}/activity").json()
    actions = [(i["actor"], i["action"]) for i in items]
    assert ("Javier", "album.created") in actions and ("Javier", "asset.uploaded") in actions
    assert ("Lucia", "invitation.accepted") in actions
    album = next(i for i in items if i["action"] == "album.created")
    assert album["detail"] == {"name": "Asturias 2025"}
    assert all("ip" not in i["detail"] for i in items)
    older = lucia.get(f"/api/v1/spaces/{space}/activity", params={"before": items[0]["id"]}).json()
    assert items[0]["id"] not in {i["id"] for i in older}
