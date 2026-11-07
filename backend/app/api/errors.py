"""Errores en formato ``application/problem+json`` (RFC 9457)."""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.observability import request_id_var

log = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"


def problem(
    status: int,
    detail: str | None = None,
    *,
    title: str | None = None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title or HTTPStatus(status).phrase,
        "status": status,
    }
    if detail:
        body["detail"] = detail
    request_id = request_id_var.get()
    if request_id:
        body["request_id"] = request_id
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


async def _http_exception(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    detail = exc.detail if isinstance(exc.detail, str) else None
    if exc.status_code == 404 and detail == "Not Found":
        detail = "No existe"
    return problem(exc.status_code, detail, headers=dict(exc.headers or {}))


async def _validation_exception(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {"loc": [str(p) for p in err.get("loc", ())], "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return problem(422, "Los datos enviados no son válidos", extra={"errors": errors})


async def _unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Error no controlado", exc_info=exc)
    return problem(500, "Algo ha fallado en el servidor. Se ha registrado el error.")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_exception)
    app.add_exception_handler(Exception, _unhandled_exception)
