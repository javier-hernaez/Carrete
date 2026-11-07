"""Migraciones: desde cero, reversión, bloqueo, volcado previo y protección de la auditoría."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import DBAPIError

from app.db.models import Base
from app.migrate import (
    MigrationError,
    current_revision,
    downgrade,
    dump_database,
    head_revision,
    is_up_to_date,
    run_migrations,
)


def test_upgrade_from_scratch(empty_engine: Engine, tmp_path: Path) -> None:
    result = run_migrations(empty_engine, data_dir=tmp_path, dump=True)
    assert result.previous is None
    assert result.current == head_revision()
    assert result.dump_path is None  # base de datos vacía: no hay nada que volcar
    assert is_up_to_date(empty_engine)
    tables = set(inspect(empty_engine).get_table_names())
    assert {"jobs", "audit_log", "alembic_version"} <= tables


def test_second_run_is_noop(engine: Engine, tmp_path: Path) -> None:
    result = run_migrations(engine, data_dir=tmp_path)
    assert not result.applied


def test_downgrade_and_upgrade_again(engine: Engine, tmp_path: Path) -> None:
    downgrade(engine, "base")
    with engine.connect() as conn:
        assert current_revision(conn) is None
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    run_migrations(engine, data_dir=tmp_path, dump=False)
    assert is_up_to_date(engine)


def test_models_match_migrations(engine: Engine) -> None:
    """Lo que declaran los modelos y lo que crean las migraciones no puede divergir."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []


def test_concurrent_runs_migrate_once(empty_engine: Engine, tmp_path: Path) -> None:
    results = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            results.append(run_migrations(empty_engine, data_dir=tmp_path, dump=False))
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert sum(1 for r in results if r.applied) == 1


def test_failed_migration_raises(engine: Engine, tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="ha fallado"):
        run_migrations(engine, data_dir=tmp_path, dump=False, target="no-existe")


def test_dump_required_when_data_exists(engine: Engine) -> None:
    with engine.begin() as conn:  # simula una base de datos con datos de una versión anterior
        conn.execute(text("UPDATE alembic_version SET version_num = 'anterior'"))
    with pytest.raises(MigrationError, match="CARRETE_DATA_DIR"):
        run_migrations(engine, data_dir=None, dump=True)


@pytest.mark.skipif(shutil.which("pg_dump") is None, reason="pg_dump no instalado")
def test_premigration_dump(engine: Engine, tmp_path: Path) -> None:
    path = dump_database(engine, tmp_path / "volcados", label="0001")
    assert path.exists()
    assert path.stat().st_size > 0
    assert not list(path.parent.glob("*.partial"))


def test_dump_without_pg_dump(engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(MigrationError, match="pg_dump"):
        dump_database(engine, tmp_path, label="x")


def test_audit_log_is_append_only(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO audit_log (id, action) VALUES (gen_random_uuid(), 'prueba')"))
    for statement in (
        "UPDATE audit_log SET action = 'otra'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ):
        with pytest.raises(DBAPIError, match="solo inserción"), engine.begin() as conn:
            conn.execute(text(statement))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT action FROM audit_log")).scalar_one() == "prueba"


def test_audit_purge_needs_explicit_permission(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO audit_log (id, action) VALUES (gen_random_uuid(), 'vieja')"))
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL carrete.audit_purge = 'on'"))
        conn.execute(text("DELETE FROM audit_log"))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one() == 0
