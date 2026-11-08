"""Dependencias comunes de las rutas: base de datos, sesión, usuario y permisos."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import AuthSession, User
from app.services import auth
from app.services.audit import RequestInfo
from app.services.errors import Forbidden, Unauthorized


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_db(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.sessions
    db = factory()
    try:
        yield db
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def request_info(request: Request) -> RequestInfo:
    # request.client ya trae la IP real si la petición llegó por un proxy de confianza
    # (uvicorn --proxy-headers con forwarded_allow_ips = CARRETE_TRUSTED_PROXIES).
    host = request.client.host if request.client else None
    try:
        ip = str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        ip = None
    return RequestInfo(
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )


DB = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ReqInfo = Annotated[RequestInfo, Depends(request_info)]


@dataclass
class Auth:
    session: AuthSession
    user: User
    token: str


def _token(request: Request, settings: Settings) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(settings.cookie_name)


def optional_auth(request: Request, db: DB, settings: SettingsDep) -> Auth | None:
    token = _token(request, settings)
    resolved = auth.resolve_session(db, token)
    if resolved is None or token is None:
        return None
    return Auth(resolved[0], resolved[1], token)


def partial_auth(current: Annotated[Auth | None, Depends(optional_auth)]) -> Auth:
    """Sesión iniciada, aunque le falte el segundo factor (solo para completarlo)."""
    if current is None:
        raise Unauthorized("Inicia sesión para continuar", code="not_authenticated")
    return current


def full_auth(current: Annotated[Auth, Depends(partial_auth)]) -> Auth:
    if current.session.stage == "totp":
        raise Unauthorized("Falta el código de verificación", code="totp_required")
    if current.session.stage == "enroll":
        raise Unauthorized("Activa la verificación en dos pasos para continuar", code="enroll_required")
    return current


def admin_auth(current: Annotated[Auth, Depends(full_auth)]) -> Auth:
    if not current.user.is_admin:
        raise Forbidden("Solo el administrador puede hacer esto")
    return current


PartialAuth = Annotated[Auth, Depends(partial_auth)]
FullAuth = Annotated[Auth, Depends(full_auth)]
AdminAuth = Annotated[Auth, Depends(admin_auth)]
OptionalAuth = Annotated[Auth | None, Depends(optional_auth)]
