"""Manejadores de tareas (procesado de medios, purga, exportaciones…)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.jobs.queue import handler

log = logging.getLogger(__name__)


@handler("noop")
def noop(_session: Session, payload: dict[str, Any]) -> None:
    """Tarea vacía: sirve para comprobar de punta a punta que la cola y el worker funcionan."""
    if payload.get("fail"):
        raise RuntimeError("Fallo pedido en la tarea de prueba")
    log.info("noop", extra={"echo": payload.get("echo")})
