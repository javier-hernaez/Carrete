"""Migraciones al arrancar.

- Un único proceso migra: ``app`` y ``worker`` arrancan a la vez y compiten por un bloqueo consultivo
  de PostgreSQL; el segundo espera y, al obtenerlo, ve que ya no queda nada pendiente.
- Antes de migrar una base de datos con datos se hace un volcado (``pg_dump``) y se verifica con
  ``pg_restore --list``. Si el volcado falla, no se migra.
- Si una migración falla, se lanza ``MigrationError`` y el proceso no llega a servir: nunca se atiende
  con el esquema a medias (cada migración va en su propia transacción).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, make_url, text

log = logging.getLogger(__name__)

# Clave arbitraria pero fija del bloqueo consultivo («carrete» en ASCII, recortado a bigint).
MIGRATION_LOCK_KEY = 0x6361727265746501
PREMIGRATION_DIR = "db-premigracion"
PREMIGRATION_KEEP = 10

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MigrationResult:
    previous: str | None
    current: str | None
    dump_path: Path | None

    @property
    def applied(self) -> bool:
        return self.previous != self.current


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def is_up_to_date(engine: Engine) -> bool:
    with engine.connect() as conn:
        return current_revision(conn) == head_revision()


def run_migrations(
    engine: Engine,
    *,
    data_dir: Path | None,
    dump: bool = True,
    target: str = "head",
) -> MigrationResult:
    """Aplica las migraciones pendientes bajo bloqueo. Devuelve qué se hizo."""
    config = alembic_config()
    with engine.connect() as conn:
        log.info("Esperando el bloqueo de migraciones")
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": MIGRATION_LOCK_KEY})
        conn.commit()
        try:
            previous = current_revision(conn)
            conn.commit()  # cierra la transacción de lectura: cada migración abre la suya
            wanted = ScriptDirectory.from_config(config).get_current_head() if target == "head" else target
            if previous == wanted:
                log.info("Esquema al día", extra={"revision": previous})
                return MigrationResult(previous, previous, None)

            dump_path: Path | None = None
            if previous is not None and dump:
                if data_dir is None:
                    raise MigrationError("Hace falta CARRETE_DATA_DIR para el volcado previo a migrar")
                dump_path = dump_database(engine, data_dir / PREMIGRATION_DIR, label=previous)

            log.info("Aplicando migraciones", extra={"from": previous, "to": wanted})
            config.attributes["connection"] = conn
            try:
                command.upgrade(config, target)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                raise MigrationError(
                    f"La migración desde {previous!r} ha fallado: {exc}. La aplicación no arranca. "
                    f"Volcado previo: {dump_path or 'no había datos'}. Ver docs/operacion.md."
                ) from exc
            current = current_revision(conn)
            log.info("Migraciones aplicadas", extra={"revision": current})
            return MigrationResult(previous, current, dump_path)
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK_KEY})
            conn.commit()


def downgrade(engine: Engine, target: str) -> None:
    config = alembic_config()
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": MIGRATION_LOCK_KEY})
        conn.commit()
        try:
            config.attributes["connection"] = conn
            command.downgrade(config, target)
            conn.commit()
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK_KEY})
            conn.commit()


def dump_database(engine: Engine, directory: Path, *, label: str) -> Path:
    """Volcado comprimido de la base de datos, verificado. Conserva los ``PREMIGRATION_KEEP`` últimos."""
    pg_dump = shutil.which("pg_dump")
    pg_restore = shutil.which("pg_restore")
    if pg_dump is None or pg_restore is None:
        raise MigrationError(
            "No se encuentra pg_dump: no se puede hacer el volcado previo a migrar. "
            "Para desactivarlo (solo en desarrollo): CARRETE_PREMIGRATION_DUMP=false"
        )
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"carrete-{stamp}-antes-de-{label}.dump"
    partial = path.with_suffix(".dump.partial")

    url = make_url(engine.url)
    env = {**os.environ, "PGCONNECT_TIMEOUT": "10"}
    if url.password:
        env["PGPASSWORD"] = str(url.password)  # nunca en la línea de órdenes (se vería con ps)
    conninfo = url.set(drivername="postgresql", password=None).render_as_string(hide_password=False)

    log.info("Volcando la base de datos antes de migrar", extra={"path": str(path)})
    try:
        subprocess.run(  # noqa: S603  # ruta absoluta resuelta con which; argumentos sin shell
            [pg_dump, "--format=custom", "--compress=6", f"--file={partial}", f"--dbname={conninfo}"],
            env=env,
            check=True,
            capture_output=True,
            timeout=3600,
        )
        subprocess.run(  # noqa: S603
            [pg_restore, "--list", str(partial)], check=True, capture_output=True, timeout=600
        )
    except subprocess.CalledProcessError as exc:
        partial.unlink(missing_ok=True)
        stderr = exc.stderr.decode(errors="replace").strip()
        raise MigrationError(f"El volcado previo a migrar ha fallado: {stderr}") from exc
    partial.rename(path)
    _prune(directory, keep=PREMIGRATION_KEEP)
    return path


def _prune(directory: Path, *, keep: int) -> None:
    dumps = sorted(directory.glob("carrete-*.dump"))
    for old in dumps[:-keep]:
        old.unlink(missing_ok=True)
