"""Fixtures comunes.

Las pruebas de integración usan un PostgreSQL real: ``CARRETE_TEST_DATABASE_URL`` (en CI, un servicio
del flujo; en local, ``make test`` levanta uno). Cada prueba que lo pide parte de un esquema vacío.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.jobs.worker import Worker
from app.main import create_app
from app.migrate import run_migrations

SECRET = "pruebas-" + "abcdefghijklmnopqrstuvwxyz0123456789"


def _test_database_url() -> str:
    url = os.environ.get("CARRETE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Sin CARRETE_TEST_DATABASE_URL: se omiten las pruebas con PostgreSQL")
    return url


@pytest.fixture
def make_settings(tmp_path: Path):  # type: ignore[no-untyped-def]
    def factory(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "environment": "test",
            "database_url": os.environ.get(
                "CARRETE_TEST_DATABASE_URL", "postgresql+psycopg://x:y@localhost:1/nada"
            ),
            "secret_key": SECRET,
            "public_url": "https://carrete.example.ts.net:10000",
            "data_dir": tmp_path / "datos",
            "premigration_dump": False,
        }
        values.update(overrides)
        return Settings(**values)  # type: ignore[arg-type]

    (tmp_path / "datos").mkdir()
    return factory


@pytest.fixture
def settings(make_settings) -> Settings:  # type: ignore[no-untyped-def]
    return make_settings()  # type: ignore[no-any-return]


@pytest.fixture
def empty_engine() -> Iterator[Engine]:
    """Motor contra una base de datos vacía (sin tablas)."""
    engine = create_engine(_test_database_url())
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    yield engine
    engine.dispose()


@pytest.fixture
def engine(empty_engine: Engine, tmp_path: Path) -> Engine:
    """Motor contra una base de datos con el esquema al día."""
    run_migrations(empty_engine, data_dir=tmp_path, dump=False)
    return empty_engine


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def make_client(settings: Settings, engine: Engine | object) -> TestClient:
    """Cliente que se comporta como la web: origen público por HTTPS y cabecera anti-CSRF."""
    return TestClient(
        create_app(settings, engine),  # type: ignore[arg-type]
        base_url=settings.public_url,
        headers={"Origin": settings.public_origin, "X-Carrete-Request": "1"},
    )


@pytest.fixture
def client(settings: Settings, engine: Engine) -> Iterator[TestClient]:
    with make_client(settings, engine) as test_client:
        yield test_client


@pytest.fixture
def new_client(settings: Settings, engine: Engine):  # type: ignore[no-untyped-def]
    """Fábrica de clientes adicionales (otra persona, otro navegador) contra la misma base de datos."""
    clients: list[TestClient] = []

    def factory() -> TestClient:
        c = make_client(settings, engine)
        c.__enter__()
        clients.append(c)
        return c

    yield factory
    for c in clients:
        c.__exit__(None, None, None)


# --- Medios ---


@pytest.fixture
def media_settings(make_settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:  # type: ignore[no-untyped-def]
    settings = make_settings(require_2fa=False)
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    return settings


@pytest.fixture
def owner(media_settings: Settings, engine: Engine):  # type: ignore[no-untyped-def]
    with make_client(media_settings, engine) as client:
        from tests.helpers import setup_admin

        yield setup_admin(client, engine)


@pytest.fixture
def worker(sessions: sessionmaker[Session]) -> Worker:
    return Worker(sessions, poll_seconds=0.01)
