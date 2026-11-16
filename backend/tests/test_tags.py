"""Etiquetas: crear, poner y quitar en lote con deshacer, filtrar, buscar, renombrar, borrar, aislamiento."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine

from tests.helpers import Person, invite, join
from tests.media_files import make_jpeg
from tests.test_organize import batch
from tests.test_uploads import upload


def ids_of(person: Person, space: str, **params: object) -> set[str]:
    items = person.get(f"/api/v1/spaces/{space}/assets", params=params).json()["items"]
    return {x["id"] for x in items}


def test_tags_end_to_end(owner: Person, tmp_path: Path, engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    space = owner.spaces["Pareja"]
    a, b, c = (
        upload(owner, space, make_jpeg(tmp_path / f"{i}.jpg", pattern=i, color=(40 * i, 90, 140)))
        for i in range(3)
    )
    url = f"/api/v1/spaces/{space}/tags"

    # Crear (con nombre normalizado) y, de paso, ponerla a una foto
    personas = owner.post(url, json={"name": "  Personas  ", "asset_ids": [a]})
    assert personas.status_code == 201, personas.text
    personas = personas.json()
    assert personas["name"] == "Personas" and personas["count"] == 1
    # El mismo nombre con otras mayúsculas es la misma etiqueta
    assert owner.post(url, json={"name": "personas"}).json()["id"] == personas["id"]
    humor = owner.post(url, json={"name": "Humor"}).json()
    assert owner.post(url, json={"name": "   "}).status_code == 422
    assert owner.post(url, json={"name": "x" * 41}).status_code == 422

    # Poner en lote: solo cuenta lo que cambia; deshacer deja cada foto como estaba
    added = batch(owner, space, [a, b], "add_tag", tag_id=personas["id"]).json()
    assert added["count"] == 1
    assert ids_of(owner, space, tag_id=personas["id"]) == {a, b}
    assert batch(owner, space, [a, b], **added["undo"]).json()["count"] == 1
    assert ids_of(owner, space, tag_id=personas["id"]) == {a}
    batch(owner, space, [a, b], "add_tag", tag_id=personas["id"])
    batch(owner, space, [b, c], "add_tag", tag_id=humor["id"])

    # Cada elemento de la lista trae sus etiquetas; el detalle, con nombre
    items = {x["id"]: x for x in owner.get(f"/api/v1/spaces/{space}/assets").json()["items"]}
    assert set(items[b]["tag_ids"]) == {personas["id"], humor["id"]}
    assert items[c]["tag_ids"] == [humor["id"]]
    assert owner.get(f"/api/v1/assets/{b}").json()["tags"] == [
        {"id": humor["id"], "name": "Humor"},
        {"id": personas["id"], "name": "Personas"},
    ]

    # Filtros: varias etiquetas a la vez (todas), sin etiqueta, y búsqueda por nombre
    assert ids_of(owner, space, tag_id=[personas["id"], humor["id"]]) == {b}
    assert ids_of(owner, space, no_tag="true") == set()
    assert ids_of(owner, space, q="humo") == {b, c}
    timeline = owner.get(f"/api/v1/spaces/{space}/timeline", params={"tag_id": humor["id"]}).json()
    assert timeline["total"] == 2

    # Quitar en lote y deshacer
    removed = batch(owner, space, [b, c], "remove_tag", tag_id=humor["id"]).json()
    assert removed["count"] == 2 and ids_of(owner, space, tag_id=humor["id"]) == set()
    batch(owner, space, [b, c], **removed["undo"])
    assert ids_of(owner, space, tag_id=humor["id"]) == {b, c}

    # Lista con recuentos de lo visible (lo descartado o en la papelera no cuenta)
    batch(owner, space, [c], "trash")
    listing = {t["name"]: t["count"] for t in owner.get(url).json()}
    assert listing == {"Humor": 1, "Personas": 2}

    # Renombrar; no se puede chocar con otra
    renamed = owner.patch(f"{url}/{humor['id']}", json={"name": "Risas"})
    assert renamed.json()["name"] == "Risas"
    assert owner.patch(f"{url}/{humor['id']}", json={"name": "PERSONAS"}).status_code == 409

    # Un lector ve las etiquetas pero no puede cambiarlas
    lector = join(new_client(), engine, invite(owner, space, "viewer"), "lector")
    assert len(lector.get(url).json()) == 2
    assert lector.post(url, json={"name": "Mía"}).status_code == 403
    assert batch(lector, space, [a], "add_tag", tag_id=personas["id"]).status_code == 403
    assert lector.delete(f"{url}/{personas['id']}").status_code == 403

    # Eliminar la etiqueta nunca elimina fotos
    assert owner.delete(f"{url}/{personas['id']}").status_code == 204
    assert owner.get(f"/api/v1/assets/{a}").status_code == 200
    assert [t["name"] for t in owner.get(url).json()] == ["Risas"]
    assert ids_of(owner, space, tag_id=personas["id"]) == set()


def test_tags_are_isolated_between_spaces(owner: Person, tmp_path: Path, engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    pareja = owner.spaces["Pareja"]
    lucia = join(new_client(), engine, invite(owner, pareja), "lucia")
    familia = lucia.post("/api/v1/spaces", json={"name": "Familia"}).json()["id"]
    suya = upload(lucia, familia, make_jpeg(tmp_path / "suya.jpg", pattern=4))
    secreta = lucia.post(
        f"/api/v1/spaces/{familia}/tags", json={"name": "Secreta", "asset_ids": [suya]}
    ).json()
    mia = upload(owner, pareja, make_jpeg(tmp_path / "mia.jpg", pattern=5))
    nuestra = owner.post(f"/api/v1/spaces/{pareja}/tags", json={"name": "Nuestra"}).json()

    # Una etiqueta de otro espacio no existe para este: ni para poner ni para filtrar ni para deshacer
    assert batch(owner, pareja, [mia], "add_tag", tag_id=secreta["id"]).status_code == 404
    undo = {"snapshot": {mia: {"has_tag": True}}, "tag_id": secreta["id"]}
    assert batch(owner, pareja, [mia], "revert", **undo).status_code == 404
    # Ni se puede poner una etiqueta propia a una foto ajena
    assert batch(lucia, familia, [mia], "add_tag", tag_id=secreta["id"]).json()["count"] == 0
    ajena = f"/api/v1/spaces/{familia}/tags/{nuestra['id']}"
    assert lucia.patch(ajena, json={"name": "x"}).status_code == 404
    # La foto ajena no recibe la etiqueta aunque se pida a través del espacio propio
    assert owner.get(f"/api/v1/assets/{mia}").json()["tags"] == []
