"""Comprobaciones de salud.

- ``/healthz``: el proceso responde. La usa Docker para reiniciar el contenedor si se cuelga.
- ``/readyz``: puede atender de verdad (base de datos accesible, esquema al día, carpeta de datos con
  permiso de escritura). No da detalles internos: solo qué comprobación falla.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine, text

from app import __version__
from app.config import Settings
from app.migrate import is_up_to_date

log = logging.getLogger(__name__)

router = APIRouter(tags=["salud"])

CheckState = Literal["ok", "fail"]


class Health(BaseModel):
    status: Literal["ok"]
    version: str


class Readiness(BaseModel):
    status: Literal["ok", "fail"]
    version: str
    checks: dict[str, CheckState]


@router.get("/healthz", response_model=Health)
def healthz() -> Health:
    return Health(status="ok", version=__version__)


@router.get("/readyz", response_model=Readiness, responses={503: {"model": Readiness}})
def readyz(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    engine: Engine = request.app.state.engine
    checks: dict[str, CheckState] = {
        "database": _check_database(engine),
        "schema": "fail",
        "data_dir": _check_data_dir(settings),
    }
    if checks["database"] == "ok":
        checks["schema"] = _check_schema(engine)
    ok = all(state == "ok" for state in checks.values())
    body = Readiness(status="ok" if ok else "fail", version=__version__, checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if ok else 503)


def _check_database(engine: Engine) -> CheckState:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        log.warning("readyz: la base de datos no responde", exc_info=True)
        return "fail"
    return "ok"


def _check_schema(engine: Engine) -> CheckState:
    try:
        return "ok" if is_up_to_date(engine) else "fail"
    except Exception:
        log.warning("readyz: no se pudo comprobar el esquema", exc_info=True)
        return "fail"


def _check_data_dir(settings: Settings) -> CheckState:
    path = settings.data_dir
    return "ok" if path.is_dir() and os.access(path, os.W_OK | os.X_OK) else "fail"
