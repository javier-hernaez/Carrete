"""Acceso a PostgreSQL: motor y sesiones de SQLAlchemy."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def build_engine(database_url: str, *, pool_size: int = 5) -> Engine:
    return create_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"connect_timeout": 5, "application_name": "carrete"},
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return build_engine(get_settings().database_url)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Sesión con transacción: confirma al salir bien y deshace ante cualquier error."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
