"""Defensa CSRF (apartados 10.3 y 14.3).

Carrete comparte nombre de equipo con otras aplicaciones (solo cambia el puerto), así que para el
navegador son «el mismo sitio» y ``SameSite`` no basta. Toda petición que modifica debe:

1. llevar la cabecera ``X-Carrete-Request: 1`` (un formulario de otro origen no puede ponerla y
   ``fetch`` entre orígenes exigiría una comprobación CORS que no se concede), y
2. traer ``Origin`` (o, si falta, ``Referer``) exactamente igual al origen público, **con puerto**.

Las peticiones con ``Authorization: Bearer`` (app Android) no usan cookies y quedan fuera.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower() if parts.scheme and parts.netloc else ""


class CSRFMiddleware:
    def __init__(self, app: ASGIApp, public_origin: str) -> None:
        self.app = app
        self.public_origin = public_origin.lower()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] in SAFE_METHODS
            or not scope["path"].startswith("/api/")
        ):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if headers.get("authorization", "").lower().startswith("bearer "):
            await self.app(scope, receive, send)
            return
        origin = headers.get("origin") or _origin_of(headers.get("referer", ""))
        if headers.get("x-carrete-request") != "1" or origin.lower() != self.public_origin:
            body = json.dumps(
                {
                    "type": "about:blank",
                    "title": "Forbidden",
                    "status": 403,
                    "detail": "Petición rechazada por seguridad (origen no permitido)",
                    "code": "csrf",
                }
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        (b"content-type", b"application/problem+json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
