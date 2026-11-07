"""Aplicación web: API bajo ``/api/v1`` y la interfaz React como ficheros estáticos."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine

from app import __version__
from app.api import health, meta
from app.api.errors import install_error_handlers, problem
from app.config import Settings, get_settings
from app.db import get_engine
from app.security.headers import RequestContextMiddleware, SecurityHeadersMiddleware

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
    )
    app.state.settings = settings
    app.state.engine = engine or get_engine()

    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(meta.router)

    @app.api_route(
        "/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False
    )
    def api_not_found(rest: str) -> Response:
        return problem(404, "No existe")

    if settings.static_dir is not None:
        _mount_web(app, settings.static_dir)

    # El último añadido es el más externo: el identificador de petición envuelve todo.
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    return app


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
