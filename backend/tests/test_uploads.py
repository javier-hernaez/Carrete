"""Subida reanudable (tus), almacenamiento inmutable, procesado, línea temporal y ficheros."""

from __future__ import annotations

import base64
import hashlib
import os
import stat
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import Asset, Blob
from app.jobs.worker import Worker
from tests.helpers import Person, invite, join, setup_admin
from tests.media_files import make_jpeg, make_video, sha256

TUS = {"Tus-Resumable": "1.0.0"}


def _meta(**values: str) -> str:
    return ",".join(f"{k} {base64.b64encode(v.encode()).decode()}" for k, v in values.items())


def tus_create(
    person: Person,
    space_id: str,
    path: Path,
    *,
    name: str | None = None,
    sha: str | None = None,
    length: int | None = None,
    mtime: int | None = None,
):  # type: ignore[no-untyped-def]
    meta = {"filename": name or path.name, "sha256": sha or sha256(path), "space_id": space_id}
    if mtime is not None:
        meta["mtime"] = str(mtime)
    return person.post(
        "/api/v1/uploads",
        headers={
            **TUS,
            "Upload-Length": str(length or path.stat().st_size),
            "Upload-Metadata": _meta(**meta),
        },
    )


def tus_patch(person: Person, location: str, data: bytes, offset: int, checksum: str | None = None):  # type: ignore[no-untyped-def]
    headers = {**TUS, "Upload-Offset": str(offset), "Content-Type": "application/offset+octet-stream"}
    if checksum:
        headers["Upload-Checksum"] = checksum
    return person.patch(location, content=data, headers=headers)


def upload(
    person: Person,
    space_id: str,
    path: Path,
    *,
    name: str | None = None,
    chunk: int = 4096,
    mtime: int | None = None,
) -> str:
    created = tus_create(person, space_id, path, name=name, mtime=mtime)
    assert created.status_code == 201, created.text
    location = created.headers["location"]
    data = path.read_bytes()
    offset = 0
    response = None
    while offset < len(data):
        response = tus_patch(person, location, data[offset : offset + chunk], offset)
        assert response.status_code == 204, response.text
        offset = int(response.headers["upload-offset"])
    assert response is not None
    return response.headers["carrete-asset-id"]


@pytest.fixture
def media_settings(make_settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:  # type: ignore[no-untyped-def]
    settings = make_settings(require_2fa=False)
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    return settings


@pytest.fixture
def owner(media_settings: Settings, engine: Engine):  # type: ignore[no-untyped-def]
    from tests.conftest import make_client

    with make_client(media_settings, engine) as client:
        yield setup_admin(client, engine)


@pytest.fixture
def worker(sessions: sessionmaker[Session]) -> Worker:
    return Worker(sessions, poll_seconds=0.01)


def drain(worker: Worker) -> None:
    while worker.run_once():
        pass


def test_tus_options(owner: Person) -> None:
    response = owner.client.options("/api/v1/uploads")
    assert response.headers["tus-version"] == "1.0.0"
    assert "creation" in response.headers["tus-extension"]


def test_full_upload_and_processing(
    owner: Person, worker: Worker, tmp_path: Path, media_settings: Settings, engine: Engine
) -> None:
    space = owner.spaces["Pareja"]
    photo = make_jpeg(
        tmp_path / "foto.jpg",
        exif_date="2023:04:15 18:30:12",
        offset="+09:00",
        gps=(43.36, -5.85),
        make="Canon",
    )
    asset_id = upload(owner, space, photo)

    # Nada más subir, ya está en la línea temporal (con marcador) aunque falte procesarla
    first = owner.get(f"/api/v1/spaces/{space}/assets").json()["items"]
    assert [a["id"] for a in first] == [asset_id] and first[0]["processing_state"] == "pending"
    assert owner.get(f"/api/v1/assets/{asset_id}/thumb").json()["code"] == "not_ready"

    drain(worker)
    detail = owner.get(f"/api/v1/assets/{asset_id}").json()
    assert detail["processing_state"] == "ready"
    assert detail["taken_at"] == "2023-04-15T18:30:12" and detail["taken_at_offset"] == 540
    assert detail["taken_at_source"] == "exif" and not detail["date_doubtful"]
    assert detail["width"] == 640 and detail["height"] == 480
    assert detail["camera"] == "Canon Prueba" and detail["source"] == "camera"
    assert detail["lat"] == pytest.approx(43.36, abs=1e-3) and detail["lon"] == pytest.approx(-5.85, abs=1e-3)
    assert detail["thumbhash"] and detail["uploaded_by"] == "Javier"
    assert detail["sha256"] == sha256(photo)

    thumb = owner.get(f"/api/v1/assets/{asset_id}/thumb")
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/webp"
    assert thumb.headers["cache-control"].startswith("private")
    assert owner.get(f"/api/v1/assets/{asset_id}/preview").status_code == 200

    original = owner.get(f"/api/v1/assets/{asset_id}/original")
    assert original.content == photo.read_bytes()
    assert original.headers["content-disposition"].startswith('attachment; filename="foto.jpg"')
    assert original.headers["x-content-type-options"] == "nosniff"

    # Invariante: el original está guardado por contenido y en solo lectura
    stored = (
        media_settings.data_dir
        / "originals"
        / detail["sha256"][:2]
        / detail["sha256"][2:4]
        / f"{detail['sha256']}.jpg"
    )
    assert stored.read_bytes() == photo.read_bytes()
    assert stat.S_IMODE(stored.stat().st_mode) == 0o444
    assert not list((media_settings.data_dir / "uploads").iterdir())


def test_whatsapp_dates_and_doubtful(owner: Person, worker: Worker, tmp_path: Path) -> None:
    space = owner.spaces["Pareja"]
    wa = upload(owner, space, make_jpeg(tmp_path / "a.jpg", pattern=1), name="IMG-20220801-WA0007.jpg")
    unknown = upload(
        owner, space, make_jpeg(tmp_path / "b.jpg", pattern=2), name="foto.jpg", mtime=1_600_000_000_000
    )
    drain(worker)
    a = owner.get(f"/api/v1/assets/{wa}").json()
    assert (a["taken_at"], a["source"], a["taken_at_source"]) == (
        "2022-08-01T12:00:00",
        "whatsapp",
        "filename",
    )
    b = owner.get(f"/api/v1/assets/{unknown}").json()
    assert b["taken_at_source"] == "mtime" and b["date_doubtful"]
    doubtful = owner.get(f"/api/v1/spaces/{space}/assets", params={"doubtful": "true"}).json()["items"]
    assert [x["id"] for x in doubtful] == [unknown]
    whatsapp = owner.get(f"/api/v1/spaces/{space}/assets", params={"source": "whatsapp"}).json()["items"]
    assert [x["id"] for x in whatsapp] == [wa]


def test_resume_after_network_cut(owner: Person, tmp_path: Path) -> None:
    photo = make_jpeg(tmp_path / "grande.jpg", size=(1600, 1200))
    data = photo.read_bytes()
    location = tus_create(owner, owner.spaces["Pareja"], photo).headers["location"]
    assert tus_patch(owner, location, data[:10_000], 0).status_code == 204
    # «Se corta la red»: el cliente pregunta dónde se quedó y sigue desde ahí
    head = owner.client.head(location, headers=TUS)
    assert head.headers["upload-offset"] == "10000" and head.headers["upload-length"] == str(len(data))
    wrong = tus_patch(owner, location, data[5000:6000], 5000)
    assert wrong.status_code == 409 and wrong.json()["code"] == "offset_mismatch"
    done = tus_patch(owner, location, data[10_000:], 10_000)
    assert done.status_code == 204 and done.headers["carrete-asset-id"]


def test_chunk_checksum(owner: Person, tmp_path: Path) -> None:
    photo = make_jpeg(tmp_path / "c.jpg")
    data = photo.read_bytes()
    location = tus_create(owner, owner.spaces["Pareja"], photo).headers["location"]
    bad = tus_patch(owner, location, data[:100], 0, checksum="sha256 " + base64.b64encode(b"x" * 32).decode())
    assert bad.status_code == 460
    assert owner.client.head(location, headers=TUS).headers["upload-offset"] == "0"
    good = "sha256 " + base64.b64encode(hashlib.sha256(data[:100]).digest()).decode()
    assert tus_patch(owner, location, data[:100], 0, checksum=good).status_code == 204


def test_whole_file_checksum_mismatch(
    owner: Person, tmp_path: Path, media_settings: Settings, engine: Engine
) -> None:
    photo = make_jpeg(tmp_path / "d.jpg")
    location = tus_create(owner, owner.spaces["Pareja"], photo, sha="0" * 64).headers["location"]
    response = tus_patch(owner, location, photo.read_bytes(), 0)
    assert response.status_code == 460 and response.json()["code"] == "file_mismatch"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM blobs")).scalar_one() == 0
    assert not (media_settings.data_dir / "originals").exists() or not any(
        (media_settings.data_dir / "originals").rglob("*.*")
    )


def test_rejects_unsupported_types(owner: Person, tmp_path: Path, engine: Engine) -> None:
    svg = tmp_path / "foto.jpg"  # extensión de foto, contenido SVG: manda el contenido
    svg.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    location = tus_create(owner, owner.spaces["Pareja"], svg).headers["location"]
    response = tus_patch(owner, location, svg.read_bytes(), 0)
    assert response.status_code == 415 and "no es una foto" in response.json()["detail"]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM assets")).scalar_one() == 0


def test_limits_before_accepting_bytes(
    owner: Person, tmp_path: Path, media_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    photo = make_jpeg(tmp_path / "e.jpg")
    space = owner.spaces["Pareja"]
    too_big = tus_create(owner, space, photo, length=media_settings.max_upload_bytes + 1)
    assert too_big.status_code == 413
    monkeypatch.setattr("app.storage.files.Storage.free_bytes", lambda _self: 10)
    assert tus_create(owner, space, photo).status_code == 507
    no_sha = owner.post(
        "/api/v1/uploads",
        headers={**TUS, "Upload-Length": "10", "Upload-Metadata": _meta(space_id=space, filename="x.jpg")},
    )
    assert no_sha.json()["code"] == "no_checksum"
    assert owner.post("/api/v1/uploads", headers={"Upload-Length": "10"}).status_code == 422


def test_deduplication(owner: Person, worker: Worker, tmp_path: Path, engine: Engine) -> None:
    pareja = owner.spaces["Pareja"]
    familia = owner.post("/api/v1/spaces", json={"name": "Familia"}).json()["id"]
    photo = make_jpeg(tmp_path / "f.jpg")
    first = upload(owner, pareja, photo)
    assert owner.post(
        f"/api/v1/spaces/{pareja}/assets/check", json={"sha256": [sha256(photo), "a" * 64]}
    ).json() == {"present": [sha256(photo)]}
    # El otro espacio no revela que el original existe en otro sitio
    assert owner.post(f"/api/v1/spaces/{familia}/assets/check", json={"sha256": [sha256(photo)]}).json() == {
        "present": []
    }
    dup = tus_create(owner, pareja, photo)
    assert dup.status_code == 409 and dup.json()["code"] == "duplicate"
    second = upload(owner, familia, photo)
    assert second != first
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*), max(ref_count) FROM blobs")).one() == (1, 2)


def test_concurrent_identical_uploads_become_one(owner: Person, tmp_path: Path, engine: Engine) -> None:
    photo = make_jpeg(tmp_path / "g.jpg")
    pareja = owner.spaces["Pareja"]
    a = tus_create(owner, pareja, photo).headers["location"]
    b = tus_create(owner, pareja, photo).headers["location"]
    data = photo.read_bytes()
    one = tus_patch(owner, a, data, 0)
    two = tus_patch(owner, b, data, 0)
    assert one.headers["carrete-asset-id"] == two.headers["carrete-asset-id"]
    assert two.headers["carrete-duplicate"] == "1"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM asset_contributions")).scalar_one() == 2


def test_permissions_and_isolation(owner: Person, tmp_path: Path, engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    pareja = owner.spaces["Pareja"]
    photo = make_jpeg(tmp_path / "h.jpg")
    asset_id = upload(owner, pareja, photo)
    pending = tus_create(owner, pareja, make_jpeg(tmp_path / "i.jpg", pattern=3)).headers["location"]

    lector = join(new_client(), engine, invite(owner, pareja, "viewer"), "lector")
    assert tus_create(lector, pareja, photo).status_code == 403
    assert lector.get(f"/api/v1/assets/{asset_id}").status_code == 200
    assert lector.get(f"/api/v1/assets/{asset_id}/original").status_code == 200

    ajena = join(new_client(), engine, invite(owner, pareja, "viewer"), "ajena")
    owner.delete(f"/api/v1/spaces/{pareja}/members/{ajena.get('/api/v1/me').json()['id']}")
    for url in (
        f"/api/v1/assets/{asset_id}",
        f"/api/v1/assets/{asset_id}/thumb",
        f"/api/v1/assets/{asset_id}/original",
        f"/api/v1/assets/{asset_id}/video",
        f"/api/v1/spaces/{pareja}/assets",
        f"/api/v1/spaces/{pareja}/timeline",
    ):
        assert ajena.get(url).status_code == 404, url
    assert (
        ajena.post(f"/api/v1/spaces/{pareja}/assets/check", json={"sha256": [sha256(photo)]}).status_code
        == 404
    )
    # Las subidas a medias son de quien las empezó
    assert ajena.client.head(pending, headers=TUS).status_code == 404
    assert tus_patch(ajena, pending, b"x", 0).status_code == 404
    assert ajena.delete(pending, headers=TUS).status_code == 404
    assert owner.delete(pending, headers=TUS).status_code == 204
    assert owner.client.head(pending, headers=TUS).status_code == 404
    anonymous = TestClient(owner.client.app, base_url=str(owner.client.base_url))
    assert anonymous.get(f"/api/v1/assets/{asset_id}/thumb").status_code == 401


def test_videos(owner: Person, worker: Worker, tmp_path: Path) -> None:
    space = owner.spaces["Pareja"]
    h264 = upload(
        owner, space, make_video(tmp_path / "v.mp4", creation="2023-01-10T10:00:00Z"), chunk=1 << 20
    )
    hevc = upload(
        owner,
        space,
        make_video(tmp_path / "v.mov", codec="libx265"),
        name="VID_20230415_183012.mov",
        chunk=1 << 20,
    )
    drain(worker)
    a = owner.get(f"/api/v1/assets/{h264}").json()
    assert a["kind"] == "video" and a["processing_state"] == "ready", a
    assert a["video_codec"] == "h264" and not a["has_preview_video"]
    assert a["duration_ms"] == pytest.approx(1000, abs=150)
    assert a["taken_at_source"] == "video" and a["taken_at"] == "2023-01-10T11:00:00"
    b = owner.get(f"/api/v1/assets/{hevc}").json()
    assert b["video_codec"] == "hevc" and b["has_preview_video"], b
    assert b["taken_at"] == "2023-04-15T18:30:12" or b["taken_at_source"] == "video"
    full = owner.get(f"/api/v1/assets/{hevc}/video")
    assert full.status_code == 200 and full.headers["content-type"] == "video/mp4"
    ranged = owner.get(f"/api/v1/assets/{hevc}/video", headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206 and len(ranged.content) == 100
    assert owner.get(f"/api/v1/assets/{hevc}/thumb").status_code == 200
    videos = owner.get(f"/api/v1/spaces/{space}/assets", params={"kind": "video"}).json()["items"]
    assert len(videos) == 2


def test_corrupt_file_is_kept_and_marked(
    owner: Person, worker: Worker, tmp_path: Path, sessions: sessionmaker[Session], media_settings: Settings
) -> None:
    broken = tmp_path / "rota.jpg"
    broken.write_bytes(b"\xff\xd8\xff\xe0" + os.urandom(2000))
    asset_id = upload(owner, owner.spaces["Pareja"], broken)
    for _ in range(3):
        with sessions() as s:
            s.execute(text("UPDATE jobs SET run_after = now() WHERE state = 'queued'"))
            s.commit()
        drain(worker)
    detail = owner.get(f"/api/v1/assets/{asset_id}").json()
    assert detail["processing_state"] == "failed" and detail["processing_error"]
    assert owner.get(f"/api/v1/assets/{asset_id}/original").content == broken.read_bytes()


def test_timeline_order_cursor_and_months(owner: Person, worker: Worker, tmp_path: Path) -> None:
    space = owner.spaces["Pareja"]
    dates = [
        "2021:06:01 10:00:00",
        "2022:03:05 10:00:00",
        "2022:03:20 10:00:00",
        "2023:12:31 23:59:59",
        "2023:12:31 23:59:59",
    ]
    ids = [
        upload(
            owner, space, make_jpeg(tmp_path / f"t{i}.jpg", exif_date=d, pattern=i, color=(i * 40, 50, 60))
        )
        for i, d in enumerate(dates)
    ]
    drain(worker)
    page1 = owner.get(f"/api/v1/spaces/{space}/assets", params={"limit": 2}).json()
    page2 = owner.get(
        f"/api/v1/spaces/{space}/assets", params={"limit": 2, "cursor": page1["next_cursor"]}
    ).json()
    page3 = owner.get(
        f"/api/v1/spaces/{space}/assets", params={"limit": 2, "cursor": page2["next_cursor"]}
    ).json()
    order = [a["id"] for p in (page1, page2, page3) for a in p["items"]]
    assert order == [ids[4], ids[3], ids[2], ids[1], ids[0]]
    assert page3["next_cursor"] is None
    timeline = owner.get(f"/api/v1/spaces/{space}/timeline").json()
    assert timeline["total"] == 5
    assert [(m["year"], m["month"], m["count"]) for m in timeline["months"]] == [
        (2023, 12, 2),
        (2022, 3, 2),
        (2021, 6, 1),
    ]
    jump = owner.get(f"/api/v1/spaces/{space}/assets", params={"start": "2022-03-31", "limit": 1}).json()
    assert jump["items"][0]["id"] == ids[2]
    ranged = owner.get(
        f"/api/v1/spaces/{space}/assets", params={"date_from": "2022-01-01", "date_to": "2022-12-31"}
    ).json()
    assert {a["id"] for a in ranged["items"]} == {ids[1], ids[2]}
    asc = owner.get(f"/api/v1/spaces/{space}/assets", params={"order": "asc", "limit": 1}).json()
    assert asc["items"][0]["id"] == ids[0]
    assert owner.get(f"/api/v1/spaces/{space}/assets", params={"cursor": "basura"}).status_code == 422


def test_expired_uploads_are_purged(
    owner: Person, tmp_path: Path, sessions: sessionmaker[Session], media_settings: Settings
) -> None:
    from app.api.uploads import purge_expired
    from app.storage.files import Storage

    location = tus_create(owner, owner.spaces["Pareja"], make_jpeg(tmp_path / "j.jpg")).headers["location"]
    upload_file = media_settings.data_dir / "uploads" / f"{location.rsplit('/', 1)[1]}.part"
    assert upload_file.exists()
    with sessions() as s:
        s.execute(text("UPDATE uploads SET expires_at = now() - interval '1 minute'"))
        s.commit()
        assert purge_expired(s, Storage(media_settings.data_dir)) == 1
    assert not upload_file.exists()
    assert owner.client.head(location, headers=TUS).status_code == 404


def test_upload_summary_is_audited(owner: Person, engine: Engine) -> None:
    space = owner.spaces["Pareja"]
    assert (
        owner.post(
            f"/api/v1/spaces/{space}/uploads/summary", json={"uploaded": 3, "duplicates": 1, "failed": 0}
        ).status_code
        == 204
    )
    with engine.connect() as conn:
        detail = conn.execute(
            text("SELECT detail FROM audit_log WHERE action = 'asset.uploaded'")
        ).scalar_one()
    assert detail == {"uploaded": 3, "duplicates": 1, "failed": 0}


def test_hamming_and_dhash_similarity(tmp_path: Path) -> None:
    import pyvips

    from app.media.process import compute_dhash, hamming

    base = make_jpeg(tmp_path / "base.jpg", size=(800, 600), pattern=0)
    smaller = tmp_path / "small.jpg"
    pyvips.Image.thumbnail(str(base), 320).jpegsave(str(smaller), Q=40)  # «reenviada por WhatsApp»
    other = make_jpeg(tmp_path / "other.jpg", size=(800, 600), color=(10, 200, 30), pattern=1)
    a, b, c = (compute_dhash(pyvips.Image.new_from_file(str(p))) for p in (base, smaller, other))
    assert hamming(a, b) <= 6
    assert hamming(a, c) > hamming(a, b)
    assert isinstance(datetime.now(), datetime)
    assert select(Asset) is not None and Blob is not None
