"""Aplicación web: API bajo ``/api/v1`` y la interfaz React como ficheros estáticos."""

from __future__ import annotations

import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app import __version__
from app.api import (
    admin,
    albums,
    android,
    assets,
    auth,
    duplicates,
    exports,
    health,
    map,
    meta,
    spaces,
    uploads,
)
from app.api.errors import install_error_handlers, problem
from app.config import Settings, get_settings
from app.db import get_engine
from app.security.csrf import CSRFMiddleware
from app.security.headers import RequestContextMiddleware, SecurityHeadersMiddleware

log = logging.getLogger(__name__)

# Rutas que nunca son la web: si no existen, 404 en problem+json en lugar de devolver index.html.
_NON_SPA_PREFIXES = ("/api/", "/healthz", "/readyz", "/assets/")


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    is_dev = settings.environment != "production"
    app = FastAPI(
        title="Carrete",
        version=__version__,
        description="API de Carrete: reunir, ordenar y conservar fotos y vídeos.",
        # La documentación interactiva solo en desarrollo: en producción no se anuncia la superficie.
        docs_url="/api/docs" if is_dev else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if is_dev else None,
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine or get_engine()
    app.state.sessions = sessionmaker(bind=app.state.engine, expire_on_commit=False)
    # Código del asistente inicial: el configurado o uno aleatorio por arranque.
    configured = settings.setup_token.get_secret_value() if settings.setup_token else None
    app.state.setup_token = configured or secrets.token_hex(12)
    app.state.setup_token_generated = configured is None

    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(meta.router)
    app.include_router(auth.router)
    app.include_router(spaces.router)
    app.include_router(admin.router)
    app.include_router(uploads.router)
    app.include_router(assets.router)
    app.include_router(albums.router)
    app.include_router(duplicates.router)
    app.include_router(exports.router)
    app.include_router(android.router)
    app.include_router(map.router)

    @app.api_route(
        "/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False
    )
    def api_not_found(rest: str) -> Response:
        return problem(404, "No existe")

    if settings.static_dir is not None:
        _mount_web(app, settings.static_dir)

    # El último añadido es el más externo: el identificador de petición envuelve todo.
    app.add_middleware(CSRFMiddleware, public_origin=settings.public_origin)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    return app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    _announce_setup(app)
    yield


def _announce_setup(app: FastAPI) -> None:
    """Si aún no hay cuentas, imprime el código del asistente en el registro del contenedor."""
    from app.services.invitations import setup_needed

    try:
        with app.state.sessions() as db:
            needed = setup_needed(db)
    except Exception:  # la base de datos puede no estar lista; /readyz lo dirá
        return
    if needed and app.state.setup_token_generated:
        log.warning(
            "Carrete aún no tiene cuentas. Abre la aplicación y usa este código de arranque: %s",
            app.state.setup_token,
            extra={"setup_token": app.state.setup_token},
        )


def _mount_web(app: FastAPI, static_dir: Path) -> None:
    index = static_dir / "index.html"
    assets = static_dir / "assets"
    if assets.is_dir():
        # Ficheros con hash en el nombre: se pueden cachear para siempre.
        app.mount("/assets", _ImmutableStaticFiles(directory=assets), name="assets")

    root = static_dir.resolve()

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str, request: Request) -> Response:
        if request.url.path.startswith(_NON_SPA_PREFIXES):
            return problem(404, "No existe")
        if path:
            candidate = (root / path).resolve()
            # Ficheros sueltos de la raíz (manifiesto, iconos, service worker), sin salir de la carpeta.
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate, headers={"cache-control": "no-cache"})
        if not index.is_file():
            return problem(404, "La interfaz web no está compilada")
        return FileResponse(index, headers={"cache-control": "no-cache"})


class _ImmutableStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        response = super().file_response(*args, **kwargs)
        response.headers["cache-control"] = "public, max-age=31536000, immutable"
        return response
