"""Errores de dominio. Las rutas no construyen respuestas de error: lanzan estos y un manejador los
convierte en ``problem+json`` con un ``code`` estable que la web puede interpretar."""

from __future__ import annotations

from typing import Any


class ServiceError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.extra = extra


class NotFound(ServiceError):
    """También para lo ajeno: un identificador de otro espacio da 404, no 403."""

    status = 404
    code = "not_found"


class Forbidden(ServiceError):
    status = 403
    code = "forbidden"


class Unauthorized(ServiceError):
    status = 401
    code = "unauthorized"


class Conflict(ServiceError):
    status = 409
    code = "conflict"


class Invalid(ServiceError):
    status = 422
    code = "invalid"


class RateLimited(ServiceError):
    status = 429
    code = "rate_limited"


class ReauthRequired(ServiceError):
    status = 403
    code = "reauth_required"
