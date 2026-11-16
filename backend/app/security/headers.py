"""Cabeceras de seguridad e identificador de petición, como middleware ASGI puro.

ASGI puro y no ``BaseHTTPMiddleware``: no almacena las respuestas en memoria, así que las descargas de
originales y exportaciones grandes siguen saliendo en flujo.
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from collections.abc import Iterable
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings
from app.observability import request_id_var

log = logging.getLogger("carrete.access")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def build_csp(settings: Settings) -> str:
    connect = ["'self'"]
    img = ["'self'", "blob:", "data:"]
    if settings.map_style_url:
        parts = urlsplit(settings.map_style_url)
        origin = f"{parts.scheme}://{parts.netloc}"
        connect.append(origin)
        img.append(origin)
    directives = {
        "default-src": ["'self'"],
        # 'wasm-unsafe-eval' solo permite compilar WebAssembly (SHA-256 de ficheros grandes al subir);
        # sigue prohibido eval() de JavaScript y cualquier script en línea.
        "script-src": ["'self'", "'wasm-unsafe-eval'"],
        "style-src": ["'self'"],
        "img-src": img,
        "media-src": ["'self'", "blob:"],
        "font-src": ["'self'"],
        "connect-src": connect,
        "worker-src": ["'self'", "blob:"],
        "manifest-src": ["'self'"],
        "object-src": ["'none'"],
        "base-uri": ["'none'"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'none'"],
    }
    return "; ".join(f"{name} {' '.join(values)}" for name, values in directives.items())


def security_headers(settings: Settings) -> list[tuple[bytes, bytes]]:
    headers = {
        "content-security-policy": build_csp(settings),
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "same-origin",
        "cross-origin-opener-policy": "same-origin",
        "cross-origin-resource-policy": "same-origin",
        "permissions-policy": (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
            "interest-cohort=(), browsing-topics=()"
        ),
    }
    if settings.is_https:
        headers["strict-transport-security"] = "max-age=31536000"
    return [(k.encode(), v.encode()) for k, v in headers.items()]


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.headers = security_headers(settings)
        self._names = {name for name, _ in self.headers}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        api = scope.get("path", "").startswith("/api/")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing = [(k, v) for k, v in message.get("headers", []) if k.lower() not in self._names]
                # Datos de la API (listas, detalles): privados y siempre frescos. Las fotos y miniaturas
                # ya traen su propia caché privada.
                if api and not any(k.lower() == b"cache-control" for k, _ in existing):
                    existing.append((b"cache-control", b"private, no-store"))
                message["headers"] = existing + self.headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestContextMiddleware:
    """Asigna un identificador a cada petición, lo devuelve en ``X-Request-ID`` y registra el acceso."""

    def __init__(self, app: ASGIApp, quiet_paths: Iterable[str] = ("/healthz",)) -> None:
        self.app = app
        self.quiet_paths = frozenset(quiet_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers", [])).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else secrets.token_hex(8)
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", [])
                message["headers"] = [*message["headers"], (b"x-request-id", request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            path = scope.get("path", "")
            if path not in self.quiet_paths:
                log.info(
                    "%s %s %s",
                    scope.get("method"),
                    path,
                    status,
                    extra={
                        "method": scope.get("method"),
                        "path": path,  # sin parámetros de consulta: pueden llevar datos
                        "status": status,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    },
                )
            request_id_var.reset(token)
