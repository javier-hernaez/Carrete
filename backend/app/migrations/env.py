"""Entorno de Alembic.

Las migraciones se aplican desde ``app.migrate`` (al arrancar, con bloqueo y volcado previo), que pasa
la conexión ya abierta en ``config.attributes["connection"]``. Para generar una revisión nueva en
desarrollo: ``alembic -c app/alembic.ini revision --autogenerate -m "descripción"``.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection, create_engine

from app.db.models import Base

config = context.config
target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    from app.config import get_settings

    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        _run(conn)
        conn.commit()


if context.is_offline_mode():
    raise SystemExit("Carrete no usa migraciones en modo offline")
run_migrations_online()
