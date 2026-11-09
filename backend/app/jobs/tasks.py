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
