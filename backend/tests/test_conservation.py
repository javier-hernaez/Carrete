"""Papelera y purga, copias, manifiestos, integridad, restauración y estado."""

from __future__ import annotations

import errno
import json
import os
import re
from pathlib import Path

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.backup.agent import BackupAgent, restore
from app.config import Settings
from app.db.models import Blob
from app.jobs.worker import Worker
from tests.helpers import PASSWORD, Person, invite, join, totp_code
from tests.media_files import make_jpeg, sha256
from tests.test_uploads import drain, upload

APP = Path(__file__).resolve().parent.parent / "app"


@pytest.fixture
def agent(
    engine: Engine, sessions: sessionmaker[Session], media_settings: Settings, tmp_path: Path
) -> BackupAgent:
    return BackupAgent(engine, sessions, source=media_settings.data_dir, target=tmp_path / "copias")


def _original(settings: Settings, sha: str, ext: str = "jpg") -> Path:
    return settings.data_dir / "originals" / sha[:2] / sha[2:4] / f"{sha}.{ext}"


def _batch(person: Person, space: str, ids: list[str], action: str):  # type: ignore[no-untyped-def]
    return person.post(f"/api/v1/spaces/{space}/assets/batch", json={"ids": ids, "action": action})


def test_trash_and_roles(owner: Person, worker: Worker, tmp_path: Path, engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    space = owner.spaces["Pareja"]
    a = upload(owner, space, make_jpeg(tmp_path / "a.jpg", pattern=1))
    b = upload(owner, space, make_jpeg(tmp_path / "b.jpg", pattern=2))
    colab = join(new_client(), engine, invite(owner, space, "collaborator"), "colab")
    lector = join(new_client(), engine, invite(owner, space, "viewer"), "lector")

    assert _batch(lector, space, [a], "trash").status_code == 403
    assert _batch(colab, space, [a, "00000000-0000-7000-8000-000000000000"], "trash").json() == {"count": 1}
    listed = [x["id"] for x in owner.get(f"/api/v1/spaces/{space}/assets").json()["items"]]
    assert listed == [b]
    trashed = [
        x["id"]
        for x in owner.get(f"/api/v1/spaces/{space}/assets", params={"trashed": "true"}).json()["items"]
    ]
    assert trashed == [a]
    assert owner.get(f"/api/v1/spaces/{space}/trash").json() == {"count": 1}
    # Restaurar lo de otros es cosa del propietario; cada uno puede deshacer lo suyo
    assert _batch(lector, space, [a], "restore").status_code == 403
    _batch(owner, space, [b], "trash")
    assert _batch(colab, space, [a, b], "restore").json() == {"count": 1}
    assert _batch(owner, space, [b], "restore").json() == {"count": 1}
    assert owner.get(f"/api/v1/spaces/{space}/trash").json() == {"count": 0}
    assert _batch(owner, space, [a], "nada").status_code == 422


def test_ids_from_other_spaces_are_ignored(owner: Person, tmp_path: Path) -> None:
    pareja = owner.spaces["Pareja"]
    familia = owner.post("/api/v1/spaces", json={"name": "Familia"}).json()["id"]
    foreign = upload(owner, familia, make_jpeg(tmp_path / "x.jpg"))
    assert _batch(owner, pareja, [foreign], "trash").json() == {"count": 0}
    assert owner.get(f"/api/v1/spaces/{familia}/trash").json() == {"count": 0}


def test_empty_trash(
    owner: Person, worker: Worker, tmp_path: Path, media_settings: Settings, engine: Engine
) -> None:
    pareja = owner.spaces["Pareja"]
    familia = owner.post("/api/v1/spaces", json={"name": "Familia"}).json()["id"]
    shared = make_jpeg(tmp_path / "compartida.jpg", pattern=1)
    alone = make_jpeg(tmp_path / "sola.jpg", pattern=2)
    a = upload(owner, pareja, shared)
    upload(owner, familia, shared)
    b = upload(owner, pareja, alone)
    drain(worker)
    _batch(owner, pareja, [a, b], "trash")

    wrong = owner.post(f"/api/v1/spaces/{pareja}/trash/empty", json={"confirm_name": "pareja"})
    assert wrong.status_code == 422 and wrong.json()["code"] == "confirm_mismatch"
    with engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET reauth_at = now() - interval '1 hour'"))
    assert (
        owner.post(f"/api/v1/spaces/{pareja}/trash/empty", json={"confirm_name": "Pareja"}).json()["code"]
        == "reauth_required"
    )
    with engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET reauth_at = now()"))
    assert owner.post(f"/api/v1/spaces/{pareja}/trash/empty", json={"confirm_name": "Pareja"}).json() == {
        "count": 2
    }

    # El original compartido sigue (lo usa Familia); el otro se ha borrado del disco
    assert _original(media_settings, sha256(shared)).exists()
    assert not _original(media_settings, sha256(alone)).exists()
    assert not (media_settings.data_dir / "derivatives" / sha256(alone)).exists()
    assert owner.get(f"/api/v1/assets/{b}").status_code == 404
    with engine.connect() as conn:
        rows = dict(conn.execute(text("SELECT sha256, ref_count FROM blobs")).tuples().all())
        purged = conn.execute(text("SELECT count(*) FROM blobs WHERE purged_at IS NOT NULL")).scalar_one()
        actions = {r[0] for r in conn.execute(text("SELECT action FROM audit_log"))}
    assert rows[sha256(shared)] == 1 and purged == 1
    assert {"trash.emptied", "asset.purged", "asset.trashed"} <= actions

    # Volver a subir algo ya purgado funciona y vuelve a necesitar copia
    upload(owner, pareja, alone)
    assert _original(media_settings, sha256(alone)).exists()
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT purged_at, backed_up_at FROM blobs WHERE sha256 = :s"), {"s": sha256(alone)}
        ).one() == (None, None)


def test_purge_after_30_days(
    owner: Person, worker: Worker, tmp_path: Path, media_settings: Settings, sessions: sessionmaker[Session]
) -> None:
    space = owner.spaces["Pareja"]
    photo = make_jpeg(tmp_path / "p.jpg")
    asset = upload(owner, space, photo)
    _batch(owner, space, [asset], "trash")

    def run_purge() -> None:
        with sessions() as s:
            from app.jobs import queue

            queue.enqueue(s, "purge_trash")
            s.commit()
        drain(worker)

    with sessions() as s:
        s.execute(text("UPDATE assets SET trashed_at = now() - interval '29 days'"))
        s.commit()
    run_purge()
    assert owner.get(f"/api/v1/assets/{asset}").status_code == 200  # día 29: se puede recuperar
    with sessions() as s:
        s.execute(text("UPDATE assets SET trashed_at = now() - interval '31 days'"))
        s.commit()
    run_purge()
    assert owner.get(f"/api/v1/assets/{asset}").status_code == 404
    assert not _original(media_settings, sha256(photo)).exists()


def test_only_purge_deletes_originals() -> None:
    """Invariante 2: ningún otro módulo borra originales."""
    offenders = []
    for path in APP.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if re.search(r"original_path\([^)]*\)\s*\.unlink", source) and path.name != "purge.py":
            offenders.append(str(path.relative_to(APP)))
        if re.search(r"rmtree\([^)]*originals", source):
            offenders.append(str(path.relative_to(APP)))
    assert offenders == []
    # Y ningún código abre un original para escribir
    for path in APP.rglob("*.py"):
        assert not re.search(
            r"original_path\([^)]*\)\s*\.open\(\s*[\"'][wa+]", path.read_text(encoding="utf-8")
        ), path


def test_backup_mirror_with_hardlinks(
    owner: Person, agent: BackupAgent, tmp_path: Path, media_settings: Settings, engine: Engine
) -> None:
    photo = make_jpeg(tmp_path / "m.jpg")
    upload(owner, owner.spaces["Pareja"], photo)
    counts = agent.mirror_originals()
    assert counts["linked"] == 1 and counts["missing"] == 0
    original = _original(media_settings, sha256(photo))
    copy = agent.backup_original_path(sha256(photo), "jpg")
    assert os.path.samefile(original, copy)  # enlace duro: no ocupa espacio
    assert agent.mirror_originals()["linked"] == 0  # nada pendiente
    with engine.connect() as conn:
        assert conn.execute(text("SELECT backed_up_at IS NOT NULL FROM blobs")).scalar_one()
        assert conn.execute(text("SELECT ok FROM backup_runs WHERE kind = 'originals'")).scalars().all() == [
            True,
            True,
        ]


def test_backup_copies_when_links_are_impossible(
    owner: Person, agent: BackupAgent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    photo = make_jpeg(tmp_path / "usb.jpg")
    upload(owner, owner.spaces["Pareja"], photo)

    def no_link(*_args: object) -> None:
        raise OSError(errno.EXDEV, "otro disco")

    monkeypatch.setattr(os, "link", no_link)
    assert agent.mirror_originals()["copied"] == 1
    copy = agent.backup_original_path(sha256(photo), "jpg")
    assert copy.read_bytes() == photo.read_bytes()
    assert oct(copy.stat().st_mode & 0o777) == "0o444"


def test_database_dumps_and_retention(agent: BackupAgent, engine: Engine) -> None:
    first = agent.dump_database()
    assert first is not None and first.exists()
    db_dir = agent.target / "db"
    assert len(list((db_dir / "diarias").glob("*.dump"))) == 1
    assert len(list((db_dir / "mensuales").glob("*.dump"))) == 1
    assert os.path.samefile(first, next((db_dir / "diarias").glob("*.dump")))
    for i in range(50):  # simula muchas horas
        (db_dir / "horarias" / f"carrete-20200101T{i:02d}0000Z.dump").write_bytes(b"x")
    agent.dump_database()
    assert len(list((db_dir / "horarias").glob("*.dump"))) == 48
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT count(*) FROM backup_runs WHERE kind = 'database' AND ok")).scalar_one()
            == 2
        )


def test_manifests_and_config(owner: Person, worker: Worker, agent: BackupAgent, tmp_path: Path) -> None:
    space = owner.spaces["Pareja"]
    upload(owner, space, make_jpeg(tmp_path / "IMG-20230415-WA0001.jpg"))
    drain(worker)
    config = tmp_path / "config"
    config.mkdir()
    (config / "docker-compose.yml").write_text("services: {}\n")
    (config / ".env").write_text("# comentario\nPOSTGRES_PASSWORD=secreto\nCARRETE_SECRET_KEY=muysecreto\n")
    agent.config_dir = config
    assert agent.write_manifests() == 1
    manifest = next((agent.target / "manifests" / space).glob("*.jsonl"))
    lines = [json.loads(line) for line in manifest.read_text().splitlines()]
    assert lines[0]["space"] == "Pareja"
    assert lines[1]["original_filename"] == "IMG-20230415-WA0001.jpg"
    assert lines[1]["taken_at"] == "2023-04-15T12:00:00" and lines[1]["uploaded_by"] == "Javier"
    env_copy = (agent.target / "config" / "env-variables.txt").read_text()
    assert env_copy.split() == ["POSTGRES_PASSWORD", "CARRETE_SECRET_KEY"] and "secreto" not in env_copy


def test_integrity_detects_corruption_and_orphans(
    owner: Person, agent: BackupAgent, tmp_path: Path, media_settings: Settings, admin_notices=None
) -> None:
    good = make_jpeg(tmp_path / "bien.jpg", pattern=1)
    bad = make_jpeg(tmp_path / "mal.jpg", pattern=2)
    space = owner.spaces["Pareja"]
    upload(owner, space, good)
    upload(owner, space, bad)
    assert agent.verify_integrity().ok

    # Se corrompe un original a propósito (sin tocar su copia: se hace en un fichero nuevo)
    target = _original(media_settings, sha256(bad))
    target.unlink()
    target.write_bytes(b"\xff\xd8\xff" + b"basura")
    (media_settings.data_dir / "originals" / "zz").mkdir(parents=True)
    (media_settings.data_dir / "originals" / "zz" / "huérfano.jpg").write_bytes(b"x")
    run = agent.verify_integrity()
    kinds = sorted(p["type"] for p in run.problems)
    assert not run.ok and kinds == ["corrupt_original", "orphan_file"]
    notices = owner.get("/api/v1/admin/notices").json()
    assert any(n["kind"] == "integrity" and n["severity"] == "critical" for n in notices)
    status = owner.get("/api/v1/admin/status").json()
    assert status["integrity"]["ok"] is False and status["integrity"]["checked"] == 2


def test_restore_from_scratch(
    owner: Person,
    worker: Worker,
    agent: BackupAgent,
    tmp_path: Path,
    media_settings: Settings,
    engine: Engine,
    sessions: sessionmaker[Session],
) -> None:
    """Prueba de restauración: crear → copiar → destruir → restaurar → comprobar."""
    space = owner.spaces["Pareja"]
    photos = [
        make_jpeg(tmp_path / f"r{i}.jpg", pattern=i, exif_date=f"2022:0{i + 1}:01 10:00:00") for i in range(3)
    ]
    ids = sorted(upload(owner, space, p) for p in photos)
    drain(worker)
    before = owner.get(f"/api/v1/spaces/{space}/assets").json()["items"]
    agent.run_once()
    dump = next((agent.target / "db" / "horarias").glob("*.dump"))

    # Desastre: se pierde la base de datos y la carpeta de originales y derivados
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    for folder in ("originals", "derivatives"):
        for path in sorted((media_settings.data_dir / folder).rglob("*"), reverse=True):
            if path.is_file():
                path.chmod(0o644)
                path.unlink()

    counts = restore(engine, sessions, dump=dump, source=media_settings.data_dir, target=agent.target)
    assert counts == {"restored_originals": 3, "missing": 0, "reprocess": 3}
    for photo in photos:
        assert _original(media_settings, sha256(photo)).read_bytes() == photo.read_bytes()
    drain(worker)

    # La sesión también estaba en la copia: la misma persona sigue dentro y ve lo mismo
    after = owner.get(f"/api/v1/spaces/{space}/assets").json()["items"]
    assert sorted(a["id"] for a in after) == ids
    assert [(a["id"], a["taken_at"]) for a in after] == [(a["id"], a["taken_at"]) for a in before]
    assert all(owner.get(f"/api/v1/assets/{i}/thumb").status_code == 200 for i in ids)
    assert agent.verify_integrity().ok


def test_purged_originals_stay_30_more_days_in_backup(
    owner: Person, agent: BackupAgent, tmp_path: Path, sessions: sessionmaker[Session]
) -> None:
    photo = make_jpeg(tmp_path / "x.jpg")
    space = owner.spaces["Pareja"]
    asset = upload(owner, space, photo)
    agent.mirror_originals()
    _batch(owner, space, [asset], "trash")
    owner.post(f"/api/v1/spaces/{space}/trash/empty", json={"confirm_name": "Pareja"})
    copy = agent.backup_original_path(sha256(photo), "jpg")
    agent.mirror_originals()
    assert copy.exists()  # recién purgado: la copia se conserva
    with sessions() as s:
        s.execute(text("UPDATE blobs SET purged_at = now() - interval '31 days'"))
        s.commit()
    assert agent.mirror_originals()["released"] == 1
    assert not copy.exists()


def test_health_checks_and_status(
    owner: Person,
    tmp_path: Path,
    sessions: sessionmaker[Session],
    media_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections import namedtuple

    from app.services.status import health_checks, storage_report
    from app.storage.files import Storage

    upload(owner, owner.spaces["Pareja"], make_jpeg(tmp_path / "s.jpg"))
    storage = Storage(media_settings.data_dir)
    with sessions() as s:
        s.execute(text("UPDATE blobs SET created_at = now() - interval '1 hour'"))
        report = storage_report(s, storage)
        assert report["spaces"][0]["count"] == 1 and report["originals"] > 0
        Usage = namedtuple("Usage", "total used free")
        monkeypatch.setattr("app.services.status.shutil.disk_usage", lambda _p: Usage(100, 95, 5))
        raised = health_checks(s, storage)
        s.commit()
    assert set(raised) == {"disk_critical", "backup_late", "originals_not_backed_up"}
    status = owner.get("/api/v1/admin/status").json()
    assert status["backup"]["pending_originals"] == 1
    assert status["storage"]["spaces"][0]["name"] == "Pareja"
    assert status["open_notices"] >= 3
    assert "version" in status and "queue" in status


def test_scheduler_enqueues_periodic_tasks(sessions: sessionmaker[Session]) -> None:
    from app.jobs.schedule import enqueue_due

    with sessions() as s:
        assert set(enqueue_due(s)) == {"purge_trash", "storage_report", "health_checks"}
        assert enqueue_due(s) == []  # no se repiten hasta que toque


def test_backup_cli_commands(
    owner: Person,
    tmp_path: Path,
    media_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app import cli, db

    upload(owner, owner.spaces["Pareja"], make_jpeg(tmp_path / "c.jpg"))
    settings = media_settings.model_copy(
        update={
            "backup_source_dir": media_settings.data_dir,
            "backup_target_dir": tmp_path / "copias",
            "config_dir": None,
            "log_format": "text",
        }
    )
    monkeypatch.setattr("app.cli.get_settings", lambda: settings)
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    monkeypatch.setattr(db, "get_sessionmaker", lambda: sessionmaker(bind=engine, expire_on_commit=False))
    cli.main(["backup"])
    out = capsys.readouterr().out
    assert "Volcado:" in out and "'linked': 1" in out and "Manifiestos: 1" in out
    cli.main(["verify"])
    assert "todo bien" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["restore", "--dump", "/no/existe.dump"])
    assert select(Blob) is not None and PASSWORD and totp_code
