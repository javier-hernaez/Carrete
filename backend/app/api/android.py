"""Distribución de la app Android sin tiendas: APK firmado dentro de la imagen."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.api.deps import FullAuth, SettingsDep
from app.security.totp import qr_svg
from app.services.errors import NotFound

router = APIRouter(prefix="/api/v1/app/android", tags=["app"])


class AndroidApp(BaseModel):
    available: bool
    version_name: str | None = None
    version_code: int | None = None
    size_bytes: int | None = None


def _apk(request: Request) -> tuple[Path, dict[str, object]] | None:
    settings = request.app.state.settings
    if settings.apk_dir is None:
        return None
    folder = Path(settings.apk_dir)
    apk, meta = folder / "carrete.apk", folder / "carrete-apk.json"
    if not apk.is_file():
        return None
    data = json.loads(meta.read_text()) if meta.is_file() else {}
    return apk, data


@router.get("", response_model=AndroidApp)
def latest(request: Request, current: FullAuth) -> AndroidApp:
    """Versión disponible (la app la consulta para avisar de actualizaciones)."""
    found = _apk(request)
    if found is None:
        return AndroidApp(available=False)
    apk, meta = found
    code = meta.get("version_code")
    return AndroidApp(
        available=True,
        version_name=str(meta.get("version_name")) if meta.get("version_name") else None,
        version_code=int(code) if isinstance(code, int) else None,
        size_bytes=apk.stat().st_size,
    )


@router.get("/apk", response_class=FileResponse)
def download(request: Request, current: FullAuth) -> FileResponse:
    found = _apk(request)
    if found is None:
        raise NotFound("Esta instalación no incluye la app Android")
    return FileResponse(
        found[0],
        media_type="application/vnd.android.package-archive",
        headers={
            "Content-Disposition": 'attachment; filename="carrete.apk"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/setup-qr")
def setup_qr(current: FullAuth, settings: SettingsDep) -> Response:
    """Código QR con la dirección del servidor, para configurar la app sin teclearla."""
    return Response(
        qr_svg(f"carrete:{settings.public_url}"),
        media_type="image/svg+xml",
        headers={"Cache-Control": "private, no-store"},
    )
