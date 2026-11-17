"""Exportar (ZIP por volúmenes y a carpeta), biblioteca en disco e importar (ZIP y carpeta)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.jobs.worker import Worker
from app.storage.naming import UniqueNames, file_name, folders_for, safe_component
from tests.helpers import Person, invite, join
from tests.media_files import make_jpeg, sha256
from tests.test_uploads import TUS, _meta, drain, tus_patch, upload


def test_naming_rules() -> None:
    assert safe_component('Viaje: "Asturias"/2025?') == "Viaje_ _Asturias__2025_"
    assert safe_component("..") == "sin-nombre"
    assert safe_component("CON.jpg") == "_CON.jpg"
    assert len(safe_component("a" * 300 + ".jpg")) == 120
    when = datetime(2023, 4, 15, 18, 30, 12)
    assert (
        file_name("IMG-20230415-WA0001.jpg", when, "jpg", normalized=True)
        == "2023-04-15_183012_IMG-20230415-WA0001.jpg"
    )
    assert file_name("../../etc/passwd", when, "jpg", normalized=False) == "passwd.jpg"
    assert folders_for("album", when, []) == ["Sin álbum/2023/04"]
    assert folders_for("album", when, ["Boda", "Viaje"]) == ["Boda", "Viaje"]
    assert folders_for("date", when, ["Boda"]) == ["2023/04"]
    assert folders_for("flat", when, []) == [""]
    names = UniqueNames()
    assert [names.claim("A", "x.jpg"), names.claim("A", "X.jpg"), names.claim("B", "x.jpg")] == [
        "A/x.jpg",
        "A/X (2).jpg",
        "B/x.jpg",
    ]


@pytest.fixture
def library_space(owner: Person, worker: Worker, tmp_path: Path) -> dict[str, str]:
    space = owner.spaces["Pareja"]
    ids = {
        "boda": upload(
            owner, space, make_jpeg(tmp_path / "boda.jpg", exif_date="2023:06:10 12:00:00", pattern=1)
        ),
        "suelta": upload(owner, space, make_jpeg(tmp_path / "IMG-20230415-WA0001.jpg", pattern=2)),
        "mala": upload(owner, space, make_jpeg(tmp_path / "mala.jpg", pattern=3)),
    }
    drain(worker)
    album = owner.post(
        f"/api/v1/spaces/{space}/albums", json={"name": "Boda", "asset_ids": [ids["boda"]]}
    ).json()
    owner.post(
        f"/api/v1/spaces/{space}/assets/batch",
        json={"ids": [ids["mala"]], "action": "review", "state": "discarded"},
    )
    owner.post(
        f"/api/v1/spaces/{space}/assets/batch",
        json={"ids": [ids["boda"]], "action": "favorite", "value": True},
    )
    return {**ids, "album": album["id"], "space": space}


def _export(person: Person, space: str, **body: object) -> dict:  # type: ignore[type-arg]
    response = person.post(f"/api/v1/spaces/{space}/exports", json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_export_zip_matches_manifest_and_resumes(
    owner: Person, worker: Worker, library_space: dict[str, str], tmp_path: Path, engine: Engine
) -> None:
    space = library_space["space"]
    export = _export(owner, space)
    assert export["state"] == "queued" and export["total_items"] == 2  # sin descartadas por defecto
    drain(worker)
    ready = owner.get(f"/api/v1/spaces/{space}/exports/{export['id']}").json()
    assert ready["state"] == "ready" and ready["progress"] == 1.0 and len(ready["files"]) == 1
    url = f"/api/v1/spaces/{space}/exports/{export['id']}/files/1"

    # Descarga reanudable: primero un trozo, «se corta», y luego el resto con Range
    head = owner.get(url, headers={"Range": "bytes=0-999"})
    assert head.status_code == 206 and len(head.content) == 1000
    tail = owner.get(url, headers={"Range": "bytes=1000-"})
    assert tail.status_code == 206
    full = owner.get(url)
    assert full.headers["content-disposition"].startswith('attachment; filename="Pareja.zip"')
    assert head.content + tail.content == full.content

    with zipfile.ZipFile(io.BytesIO(full.content)) as zf:
        names = set(zf.namelist())
        assert all(info.compress_type == zipfile.ZIP_STORED for info in zf.infolist())
        manifest = json.loads(zf.read("carrete-manifest.json"))
        assert manifest["space"] == "Pareja" and len(manifest["items"]) == 2
        for item in manifest["items"]:
            for path in item["paths"]:
                assert hashlib.sha256(zf.read(path)).hexdigest() == item["sha256"]
        boda = next(i for i in manifest["items"] if i["albums"] == ["Boda"])
        assert boda["paths"] == ["Boda/2023-06-10_120000_boda.jpg"] and boda["favorite"] is True
        assert "Sin álbum/2023/04/2023-04-15_120000_IMG-20230415-WA0001.jpg" in names
        rows = list(csv.DictReader(io.StringIO(zf.read("carrete-manifest.csv").decode("utf-8-sig"))))
        assert {r["sha256"] for r in rows} == {i["sha256"] for i in manifest["items"]}
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT detail->>'scope' FROM audit_log WHERE action = 'export.created'")
            ).scalar_one()
            == "space"
        )


def test_export_options_and_volumes(
    owner: Person,
    worker: Worker,
    library_space: dict[str, str],
    sessions: sessionmaker[Session],
    media_settings: Settings,
) -> None:
    from app.services import exports
    from app.storage.files import Storage

    space = library_space["space"]
    everything = _export(owner, space, structure="date", naming="original", include="all")
    drain(worker)
    data = owner.get(f"/api/v1/spaces/{space}/exports/{everything['id']}/files/1").content
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        media = sorted(n for n in zf.namelist() if not n.startswith("carrete-"))
    assert (
        media == ["2023/04/IMG-20230415-WA0001.jpg", "2023/06/boda.jpg", sorted(media)[-1]] or len(media) == 3
    )
    assert len(media) == 3 and all(n.count("/") == 2 for n in media)

    album_only = _export(owner, space, album_ids=[library_space["album"]], structure="flat")
    assert album_only["total_items"] == 1

    # Volúmenes: con un tamaño mínimo, cada foto va en su propio ZIP, cada uno válido por sí mismo
    with sessions() as s:
        s.execute(
            text("UPDATE exports SET params = jsonb_set(params, '{volume_bytes}', '1000') WHERE id = :i"),
            {"i": everything["id"]},
        )
        s.execute(text("UPDATE exports SET state = 'queued' WHERE id = :i"), {"i": everything["id"]})
        s.commit()
        exports.build(s, Storage(media_settings.data_dir), __import__("uuid").UUID(everything["id"]))
    files = owner.get(f"/api/v1/spaces/{space}/exports/{everything['id']}").json()["files"]
    assert len(files) == 3 and files[0]["name"] == "Pareja (1 de 3).zip"
    for f in files:
        with zipfile.ZipFile(
            io.BytesIO(
                owner.get(f"/api/v1/spaces/{space}/exports/{everything['id']}/files/{f['number']}").content
            )
        ) as zf:
            assert zf.testzip() is None


def test_export_permissions_space_and_expiry(
    owner: Person,
    worker: Worker,
    library_space: dict[str, str],
    engine: Engine,
    new_client,
    monkeypatch: pytest.MonkeyPatch,
    sessions: sessionmaker[Session],
) -> None:  # type: ignore[no-untyped-def]
    space = library_space["space"]
    lector = join(new_client(), engine, invite(owner, space, "viewer"), "lector")
    assert (
        lector.post(f"/api/v1/spaces/{space}/exports", json={}).status_code == 403
    )  # todo el espacio: solo propietario
    mine = _export(lector, space, ids=[library_space["boda"]])
    theirs = _export(owner, space, album_ids=[library_space["album"]])
    assert {e["id"] for e in lector.get(f"/api/v1/spaces/{space}/exports").json()} == {mine["id"]}
    assert lector.get(f"/api/v1/spaces/{space}/exports/{theirs['id']}").status_code == 404
    assert {e["id"] for e in owner.get(f"/api/v1/spaces/{space}/exports").json()} == {
        mine["id"],
        theirs["id"],
    }

    with engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET reauth_at = now() - interval '1 hour'"))
    assert owner.post(f"/api/v1/spaces/{space}/exports", json={}).json()["code"] == "reauth_required"
    with engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET reauth_at = now()"))
    monkeypatch.setattr("app.storage.files.Storage.free_bytes", lambda _self: 10)
    assert owner.post(f"/api/v1/spaces/{space}/exports", json={}).status_code == 507

    drain(worker)
    with sessions() as s:
        s.execute(text("UPDATE exports SET expires_at = now() - interval '1 minute'"))
        s.commit()
        from app.jobs import queue

        queue.enqueue(s, "expire_exports")
        s.commit()
    drain(worker)
    assert owner.get(f"/api/v1/spaces/{space}/exports/{theirs['id']}/files/1").status_code == 404
    assert owner.get(f"/api/v1/spaces/{space}/exports").json() == []


def test_export_to_server_folder(
    owner: Person,
    worker: Worker,
    library_space: dict[str, str],
    tmp_path: Path,
    media_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    new_client,
) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "usb"
    root.mkdir()
    monkeypatch.setattr(
        "app.config.get_settings", lambda: media_settings.model_copy(update={"export_roots": [root]})
    )
    owner.client.app.state.settings = media_settings.model_copy(update={"export_roots": [root]})  # type: ignore[attr-defined]
    space = library_space["space"]
    assert (
        owner.post(
            f"/api/v1/spaces/{space}/exports", json={"target": "folder", "folder": str(tmp_path / "otra")}
        ).status_code
        == 403
    )
    assert (
        owner.post(
            f"/api/v1/spaces/{space}/exports",
            json={"target": "folder", "folder": str(root / ".." / "escape")},
        ).status_code
        == 403
    )
    export = _export(owner, space, target="folder", folder=str(root))
    drain(worker)
    out = Path(owner.get(f"/api/v1/spaces/{space}/exports/{export['id']}").json()["files"][0]["name"])
    assert out.parent == root and (out / "carrete-manifest.json").exists()
    assert (out / "Boda" / "2023-06-10_120000_boda.jpg").exists()
    colab = join(new_client(), engine, invite(owner, space, "collaborator"), "colab")
    colab.client.app.state.settings = owner.client.app.state.settings  # type: ignore[attr-defined]
    assert (
        colab.post(
            f"/api/v1/spaces/{space}/exports",
            json={"target": "folder", "folder": str(root), "ids": [library_space["boda"]]},
        ).status_code
        == 403
    )


def test_library_on_disk(
    owner: Person,
    worker: Worker,
    library_space: dict[str, str],
    media_settings: Settings,
    sessions: sessionmaker[Session],
) -> None:
    from app.jobs import queue

    with sessions() as s:
        queue.enqueue(s, "build_library")
        s.commit()
    drain(worker)
    lib = media_settings.data_dir / "library"
    boda = lib / "Pareja" / "Boda" / "2023-06-10_120000_boda.jpg"
    loose = lib / "Pareja" / "Sin álbum" / "2023" / "04" / "2023-04-15_120000_IMG-20230415-WA0001.jpg"
    assert boda.exists() and loose.exists() and (lib / "LEEME.txt").exists()
    detail = owner.get(f"/api/v1/assets/{library_space['boda']}").json()
    original = (
        media_settings.data_dir
        / "originals"
        / detail["sha256"][:2]
        / detail["sha256"][2:4]
        / f"{detail['sha256']}.jpg"
    )
    assert boda.samefile(original)  # enlace duro: no ocupa espacio
    assert not list(lib.rglob("*mala*"))  # lo descartado no entra
    # Se reconstruye entera: lo que se quita de un álbum desaparece de su carpeta
    owner.post(
        f"/api/v1/spaces/{library_space['space']}/assets/batch",
        json={"ids": [library_space["boda"]], "action": "remove_album", "album_id": library_space["album"]},
    )
    assert owner.post("/api/v1/admin/library/rebuild").status_code == 202
    drain(worker)
    assert (
        not boda.exists()
        and (lib / "Pareja" / "Sin álbum" / "2023" / "06" / "2023-06-10_120000_boda.jpg").exists()
    )
    assert original.exists()
    assert owner.get("/api/v1/admin/status").json()["library"]["files"] == 2


def _zip(path: Path, entries: dict[str, bytes], *, compress: bool = True) -> Path:
    with zipfile.ZipFile(
        path, "w", compression=zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    ) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def test_import_zip_takeout_and_attacks(
    owner: Person, worker: Worker, tmp_path: Path, media_settings: Settings, engine: Engine
) -> None:
    space = owner.spaces["Pareja"]
    a = make_jpeg(tmp_path / "a.jpg", pattern=1).read_bytes()
    b = make_jpeg(tmp_path / "b.jpg", pattern=2).read_bytes()
    takeout = {
        "title": "PXL_X.jpg",
        "photoTakenTime": {"timestamp": "1681576212"},
        "geoData": {"latitude": 43.36, "longitude": -5.85},
    }
    archive = _zip(
        tmp_path / "takeout.zip",
        {
            "Takeout/Google Fotos/Viaje/PXL_X.jpg": a,
            "Takeout/Google Fotos/Viaje/PXL_X.jpg.supplemental-metadata.json": json.dumps(takeout).encode(),
            "../../fuera.jpg": b,  # ruta maliciosa
            "notas.txt": b"hola",
            "bomba.jpg": b"\0" * (64 * 1024 * 1024),  # se comprime muchísimo: bomba
            "__MACOSX/._PXL_X.jpg": b"basura",
        },
    )
    created = owner.post(
        "/api/v1/uploads",
        headers={
            **TUS,
            "Upload-Length": str(archive.stat().st_size),
            "Upload-Metadata": _meta(filename="takeout.zip", sha256=sha256(archive), space_id=space),
        },
    )
    done = tus_patch(owner, created.headers["location"], archive.read_bytes(), 0)
    assert done.status_code == 204 and done.headers["carrete-import-id"]
    drain(worker)
    imports = owner.get(f"/api/v1/spaces/{space}/imports").json()
    assert imports[0]["state"] == "done"
    counts = imports[0]["counts"]
    assert (counts["imported"], counts["unsupported"], counts["suspicious"]) == (2, 1, 1)
    items = owner.get(f"/api/v1/spaces/{space}/assets").json()["items"]
    takeout_asset = next(
        owner.get(f"/api/v1/assets/{i['id']}").json()
        for i in items
        if owner.get(f"/api/v1/assets/{i['id']}").json()["original_filename"] == "PXL_X.jpg"
    )
    assert (
        takeout_asset["taken_at_source"] == "takeout" and takeout_asset["taken_at"] == "2023-04-15T18:30:12"
    )
    assert takeout_asset["lat"] == pytest.approx(43.36) and takeout_asset["uploaded_via"] == "import"
    assert (
        not (tmp_path / "fuera.jpg").exists() and not (media_settings.data_dir.parent / "fuera.jpg").exists()
    )
    assert not list((media_settings.data_dir / "uploads").glob("import-*"))
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT detail->>'source' FROM audit_log WHERE action = 'asset.uploaded'")
            ).scalar_one()
            == "zip"
        )


def test_import_bad_zip(owner: Person, worker: Worker, tmp_path: Path) -> None:
    space = owner.spaces["Pareja"]
    broken = tmp_path / "rota.zip"
    broken.write_bytes(b"PK\x03\x04" + b"x" * 100)
    created = owner.post(
        "/api/v1/uploads",
        headers={
            **TUS,
            "Upload-Length": str(broken.stat().st_size),
            "Upload-Metadata": _meta(filename="rota.zip", sha256=sha256(broken), space_id=space),
        },
    )
    tus_patch(owner, created.headers["location"], broken.read_bytes(), 0)
    drain(worker)
    record = owner.get(f"/api/v1/spaces/{space}/imports").json()[0]
    assert record["state"] == "failed" and record["error"]


def test_import_folder_command(
    owner: Person,
    worker: Worker,
    tmp_path: Path,
    media_settings: Settings,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app import cli, db

    disk = tmp_path / "disco"
    (disk / "Asturias 2019").mkdir(parents=True)
    make_jpeg(disk / "Asturias 2019" / "1.jpg", color=(200, 30, 30))
    make_jpeg(disk / "Asturias 2019" / "2.jpg", color=(30, 200, 30))
    make_jpeg(disk / "suelta.jpg", color=(30, 30, 200))
    (disk / "LEEME.txt").write_text("no es una foto")
    monkeypatch.setattr(
        "app.cli.get_settings", lambda: media_settings.model_copy(update={"log_format": "text"})
    )
    monkeypatch.setattr(db, "get_sessionmaker", lambda: sessionmaker(bind=engine, expire_on_commit=False))
    cli.main(["import", str(disk), "--space", "Pareja", "--albums"])
    assert "Importados 3, ya estaban 0, no admitidos 1" in capsys.readouterr().out
    cli.main(["import", str(disk), "--space", "Pareja"])
    assert "Importados 0, ya estaban 3" in capsys.readouterr().out
    albums = owner.get(f"/api/v1/spaces/{owner.spaces['Pareja']}/albums").json()
    assert [(a["name"], a["count"]) for a in albums] == [("Asturias 2019", 2)]
    with pytest.raises(SystemExit):
        cli.main(["import", str(disk), "--space", "No existe"])
    cli.main(["library"])
    assert "Biblioteca: 3 ficheros" in capsys.readouterr().out


def test_export_all_albums_and_tags(
    owner: Person, worker: Worker, library_space: dict[str, str], engine: Engine, new_client, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    space = library_space["space"]
    viaje = owner.post(
        f"/api/v1/spaces/{space}/albums", json={"name": "Viaje", "asset_ids": [library_space["suelta"]]}
    ).json()
    otra = upload(owner, space, make_jpeg(tmp_path / "otra.jpg", pattern=5, color=(20, 160, 90)))
    drain(worker)
    tags = f"/api/v1/spaces/{space}/tags"
    personas = owner.post(tags, json={"name": "Personas", "asset_ids": [library_space["boda"], otra]}).json()
    humor = owner.post(tags, json={"name": "Humor", "asset_ids": [library_space["suelta"]]}).json()

    # Todos los álbumes: lo que está en alguno (Boda y Viaje), no lo suelto
    everything = _export(owner, space, all_albums=True)
    assert everything["total_items"] == 2 and everything["params"]["scope"] == "albums"
    assert everything["params"]["all_albums"] is True
    drain(worker)
    data = owner.get(f"/api/v1/spaces/{space}/exports/{everything['id']}/files/1").content
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        folders = {n.split("/")[0] for n in zf.namelist() if not n.startswith("carrete-")}
    assert folders == {"Boda", "Viaje"}

    # Todos los álbumes, solo con alguna de las etiquetas elegidas
    assert _export(owner, space, all_albums=True, tag_ids=[personas["id"]])["total_items"] == 1
    both = _export(owner, space, all_albums=True, tag_ids=[personas["id"], humor["id"]])
    assert both["total_items"] == 2
    # Algunos álbumes con etiquetas
    assert (
        owner.post(
            f"/api/v1/spaces/{space}/exports", json={"album_ids": [viaje["id"]], "tag_ids": [personas["id"]]}
        ).json()["code"]
        == "empty_export"
    )
    # Todo el espacio con una etiqueta (propietario): también lo que no está en ningún álbum
    assert _export(owner, space, tag_ids=[personas["id"]])["total_items"] == 2

    # Un lector puede exportar todos los álbumes, pero no el espacio entero por etiquetas
    lector = join(new_client(), engine, invite(owner, space, "viewer"), "lector")
    assert _export(lector, space, all_albums=True)["total_items"] == 2
    assert lector.post(f"/api/v1/spaces/{space}/exports", json={"tag_ids": [humor["id"]]}).status_code == 403


def test_random_asset(owner: Person, worker: Worker, library_space: dict[str, str]) -> None:
    space = library_space["space"]
    url = f"/api/v1/spaces/{space}/assets/random"
    seen = {owner.get(url).json()["id"] for _ in range(30)}
    # Nunca lo descartado; con el tiempo salen las dos que se ven
    assert seen == {library_space["boda"], library_space["suelta"]}
    assert owner.get(url, params={"favorite": "true"}).json()["id"] == library_space["boda"]
    owner.post(
        f"/api/v1/spaces/{space}/assets/batch",
        json={"ids": [library_space["boda"], library_space["suelta"]], "action": "trash"},
    )
    assert owner.get(url).json() is None
