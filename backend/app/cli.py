"""Órdenes de administración: ``carrete <orden>``.

Dentro del contenedor: ``docker compose exec app carrete <orden>``.

Órdenes: ``serve``, ``worker``, ``migrate``, ``check-config`` y ``openapi``.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence

from pydantic import ValidationError

from app.config import Settings, describe_errors, get_settings

log = logging.getLogger("carrete")

EXIT_CONFIG = 2
EXIT_MIGRATION = 3


def _load_settings() -> Settings:
    try:
        return get_settings()
    except ValidationError as exc:
        print("La configuración no es válida; Carrete no arranca:", file=sys.stderr)  # noqa: T201
        for line in describe_errors(exc):
            print(f"  - {line}", file=sys.stderr)  # noqa: T201
        raise SystemExit(EXIT_CONFIG) from None


def _setup(settings: Settings) -> None:
    from app.observability import configure_logging

    configure_logging(settings.log_level, settings.log_format)


def _migrate(settings: Settings) -> None:
    from app.db import get_engine
    from app.migrate import MigrationError, run_migrations

    try:
        run_migrations(get_engine(), data_dir=settings.data_dir, dump=settings.premigration_dump)
    except MigrationError as exc:
        log.critical(str(exc))
        raise SystemExit(EXIT_MIGRATION) from None


def cmd_serve(_: argparse.Namespace) -> None:
    import uvicorn

    from app.main import create_app

    settings = _load_settings()
    _setup(settings)
    _migrate(settings)
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",  # noqa: S104  # nosec B104  # dentro del contenedor; fuera solo 127.0.0.1
        port=8000,
        proxy_headers=True,
        forwarded_allow_ips=[str(net) for net in settings.trusted_proxies],
        server_header=False,
        date_header=True,
        log_config=None,
        timeout_graceful_shutdown=25,
    )


def cmd_worker(_: argparse.Namespace) -> None:
    from app.db import get_sessionmaker
    from app.jobs.worker import Worker

    settings = _load_settings()
    _setup(settings)
    _migrate(settings)
    worker = Worker(get_sessionmaker(), poll_seconds=settings.worker_poll_seconds)
    worker.install_signal_handlers()
    worker.run_forever()


def cmd_migrate(_: argparse.Namespace) -> None:
    settings = _load_settings()
    _setup(settings)
    _migrate(settings)


def cmd_check_config(_: argparse.Namespace) -> None:
    settings = _load_settings()
    print(f"Configuración válida. Dirección pública: {settings.public_url}")  # noqa: T201


def cmd_openapi(_: argparse.Namespace) -> None:
    """Imprime la especificación OpenAPI (con ella se genera el cliente TypeScript de la web)."""
    from unittest.mock import MagicMock

    from app.main import create_app

    settings = Settings(
        environment="development",
        database_url="postgresql+psycopg://openapi@localhost/openapi",
        secret_key="openapi-" + "abcdefghijklmnopqrstuvwxyz0123456789",
        public_url="http://localhost:8010",
    )
    app = create_app(settings, engine=MagicMock())
    spec = app.openapi()
    # Versión de la API, no de la imagen: así el fichero generado no cambia en cada compilación.
    spec["info"]["version"] = "v1"
    print(json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True))  # noqa: T201


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="carrete", description="Administración de Carrete")
    sub = parser.add_subparsers(dest="command", required=True, metavar="orden")
    commands = {
        "serve": (cmd_serve, "Aplica migraciones y sirve la web y la API"),
        "worker": (cmd_worker, "Aplica migraciones y procesa la cola de tareas"),
        "migrate": (cmd_migrate, "Aplica las migraciones pendientes (con volcado previo)"),
        "check-config": (cmd_check_config, "Valida la configuración y sale"),
        "openapi": (cmd_openapi, "Imprime la especificación OpenAPI"),
    }
    for name, (fn, help_text) in commands.items():
        sub.add_parser(name, help=help_text, description=help_text).set_defaults(func=fn)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
