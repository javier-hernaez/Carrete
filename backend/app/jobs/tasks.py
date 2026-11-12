"""Manejadores de tareas (procesado de medios, purga, exportaciones…)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.jobs.queue import handler, on_final_failure

log = logging.getLogger(__name__)


@handler("noop")
def noop(_session: Session, payload: dict[str, Any]) -> None:
    """Tarea vacía: sirve para comprobar de punta a punta que la cola y el worker funcionan."""
    if payload.get("fail"):
        raise RuntimeError("Fallo pedido en la tarea de prueba")
    log.info("noop", extra={"echo": payload.get("echo")})


@handler("process_asset")
def process_asset(session: Session, payload: dict[str, Any]) -> None:
    """Procesa un elemento recién subido. Si agota los reintentos, queda marcado y se conserva."""
    import uuid

    from app.config import get_settings
    from app.media.process import process_asset as run
    from app.storage.files import Storage

    run(session, Storage(get_settings().data_dir), uuid.UUID(payload["asset_id"]))


@on_final_failure("process_asset")
def process_asset_failed(session: Session, payload: dict[str, Any], error: str) -> None:
    import uuid

    from app.services.assets import mark_processing_failed

    mark_processing_failed(session, uuid.UUID(payload["asset_id"]), error)


def _storage() -> object:
    from app.config import get_settings
    from app.storage.files import Storage

    return Storage(get_settings().data_dir)


@handler("purge_trash")
def purge_trash(session: Session, payload: dict[str, Any]) -> None:
    """Purga nocturna: elementos con más de 30 días en la papelera."""
    from app.storage.files import Storage
    from app.storage.purge import purge_expired_trash, purge_unreferenced_blobs

    storage = _storage()
    assert isinstance(storage, Storage)
    while purge_expired_trash(session, storage):
        session.flush()
    purge_unreferenced_blobs(session, storage)


@handler("storage_report")
def storage_report(session: Session, payload: dict[str, Any]) -> None:
    from app.services.status import storage_report as run
    from app.storage.files import Storage

    storage = _storage()
    assert isinstance(storage, Storage)
    run(session, storage)


@handler("health_checks")
def health_checks(session: Session, payload: dict[str, Any]) -> None:
    from app.services.status import health_checks as run
    from app.storage.files import Storage

    storage = _storage()
    assert isinstance(storage, Storage)
    run(session, storage)


@handler("build_export")
def build_export(session: Session, payload: dict[str, Any]) -> None:
    import uuid

    from app.services.exports import build
    from app.storage.files import Storage

    storage = _storage()
    assert isinstance(storage, Storage)
    build(session, storage, uuid.UUID(payload["export_id"]))


@on_final_failure("build_export")
def build_export_failed(session: Session, payload: dict[str, Any], error: str) -> None:
    import uuid

    from app.db.models import Export

    export = session.get(Export, uuid.UUID(payload["export_id"]))
    if export is not None and export.state != "ready":
        export.state = "failed"
        export.error = error[:1000]


@handler("expire_exports")
def expire_exports(session: Session, payload: dict[str, Any]) -> None:
    from app.services.exports import expire
    from app.storage.files import Storage

    storage = _storage()
    assert isinstance(storage, Storage)
    expire(session, storage)


@handler("build_library")
def build_library(session: Session, payload: dict[str, Any]) -> None:
    """Biblioteca en disco: cada noche y con el botón de Administración."""
    from datetime import UTC, datetime

    from app.config import get_settings
    from app.services.status import put_state
    from app.storage.files import Storage
    from app.storage.library import build

    if not get_settings().library_enabled:
        return
    storage = _storage()
    assert isinstance(storage, Storage)
    result = build(session, storage)
    put_state(
        session,
        "library",
        {
            "built_at": datetime.now(UTC).isoformat(),
            "spaces": result.spaces,
            "files": result.files,
            "missing": result.missing,
        },
    )


@handler("import_zip")
def import_zip(session: Session, payload: dict[str, Any]) -> None:
    import uuid

    from app.config import get_settings
    from app.services.imports import run_import
    from app.storage.files import Storage

    storage = _storage()
    assert isinstance(storage, Storage)
    settings = get_settings()
    import_id = uuid.UUID(payload["import_id"])
    run_import(
        session,
        storage,
        import_id,
        storage.uploads / f"import-{import_id}.zip",
        settings.max_upload_bytes,
        settings.min_free_bytes,
    )
