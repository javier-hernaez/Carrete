"""Información pública mínima que necesita la web antes de iniciar sesión."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import __version__
from app.config import Settings

router = APIRouter(prefix="/api/v1", tags=["meta"])


class InstanceInfo(BaseModel):
    name: str
    version: str
    map_enabled: bool
    map_style_url: str | None = None


@router.get("/info", response_model=InstanceInfo)
def instance_info(request: Request) -> InstanceInfo:
    settings: Settings = request.app.state.settings
    return InstanceInfo(
        name="Carrete",
        version=__version__,
        map_enabled=settings.map_style_url is not None,
        map_style_url=settings.map_style_url,
    )
