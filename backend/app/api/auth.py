"""Rutas de acceso: asistente inicial, inicio de sesión, segundo factor, sesiones y perfil."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import DB, FullAuth, OptionalAuth, PartialAuth, ReqInfo, SettingsDep
from app.config import Settings
from app.db.models import AuthSession
from app.services import audit, auth, invitations, spaces
from app.services.errors import NotFound

router = APIRouter(prefix="/api/v1", tags=["acceso"])

Stage = Literal["full", "totp", "enroll"]


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=int(auth.ABSOLUTE_TIMEOUT.total_seconds()),
        httponly=True,
        secure=settings.is_https,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.cookie_name, path="/", secure=settings.is_https, httponly=True, samesite="lax"
    )


class StageOut(BaseModel):
    stage: Stage


# --- Asistente inicial ---------------------------------------------------------------------------------


class SetupState(BaseModel):
    needed: bool


class SetupIn(BaseModel):
    token: str = Field(max_length=200)
    username: str = Field(max_length=64)
    display_name: str = Field(max_length=120)
    password: str = Field(max_length=512)
    space_name: str = Field(max_length=200)


@router.get("/setup", response_model=SetupState)
def setup_state(db: DB) -> SetupState:
    return SetupState(needed=invitations.setup_needed(db))


@router.post("/setup", response_model=StageOut)
def setup(
    body: SetupIn, request: Request, response: Response, db: DB, settings: SettingsDep, info: ReqInfo
) -> StageOut:
    issued = invitations.run_setup(
        db,
        settings,
        expected_token=request.app.state.setup_token,
        token=body.token,
        username=body.username,
        display_name=body.display_name,
        password=body.password,
        space_name=body.space_name,
        request=info,
    )
    db.commit()
    set_session_cookie(response, settings, issued.token)
    return StageOut(stage=issued.session.stage)  # type: ignore[arg-type]


# --- Inicio de sesión ----------------------------------------------------------------------------------


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=512)


@router.post("/auth/login", response_model=StageOut)
def login(body: LoginIn, response: Response, db: DB, settings: SettingsDep, info: ReqInfo) -> StageOut:
    issued = auth.login(db, settings, body.username, body.password, info)
    db.commit()
    set_session_cookie(response, settings, issued.token)
    return StageOut(stage=issued.session.stage)  # type: ignore[arg-type]


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)


@router.post("/auth/totp", response_model=StageOut)
def verify_totp(body: CodeIn, current: PartialAuth, db: DB, settings: SettingsDep, info: ReqInfo) -> StageOut:
    if current.session.stage != "totp":
        return StageOut(stage=current.session.stage)  # type: ignore[arg-type]
    auth.verify_second_factor(db, settings, current.session, current.user, body.code, info)
    db.commit()
    return StageOut(stage="full")


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg: str


@router.post("/auth/totp/setup", response_model=TotpSetupOut)
def totp_setup(current: PartialAuth, db: DB, settings: SettingsDep) -> TotpSetupOut:
    if current.session.stage == "totp":
        raise NotFound("No disponible")
    if current.session.stage == "full":
        auth.require_recent_auth(current.session)
    data = auth.start_totp_enrollment(db, settings, current.user)
    db.commit()
    return TotpSetupOut(**data)


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


@router.post("/auth/totp/enable", response_model=RecoveryCodesOut)
def totp_enable(
    body: CodeIn, current: PartialAuth, db: DB, settings: SettingsDep, info: ReqInfo
) -> RecoveryCodesOut:
    if current.session.stage == "totp":
        raise NotFound("No disponible")
    codes = auth.finish_totp_enrollment(db, settings, current.session, current.user, body.code, info)
    db.commit()
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/auth/totp/disable", status_code=204)
def totp_disable(current: FullAuth, db: DB, settings: SettingsDep, info: ReqInfo) -> None:
    auth.require_recent_auth(current.session)
    auth.disable_totp(db, settings, current.user, info)
    db.commit()


@router.post("/auth/recovery-codes", response_model=RecoveryCodesOut)
def regenerate_recovery_codes(current: FullAuth, db: DB, info: ReqInfo) -> RecoveryCodesOut:
    auth.require_recent_auth(current.session)
    codes = auth.replace_recovery_codes(db, current.user)
    audit.record(db, "auth.recovery_codes_regenerated", actor_id=current.user.id, request=info)
    db.commit()
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/auth/logout", status_code=204)
def logout(response: Response, current: OptionalAuth, db: DB, settings: SettingsDep, info: ReqInfo) -> None:
    if current is not None:
        auth.revoke(db, current.session)
        audit.record(db, "auth.logout", actor_id=current.user.id, request=info)
        db.commit()
    clear_session_cookie(response, settings)


class ReauthIn(BaseModel):
    password: str = Field(max_length=512)
    code: str | None = Field(default=None, max_length=20)


@router.post("/auth/reauth", status_code=204)
def reauth(body: ReauthIn, current: FullAuth, db: DB, settings: SettingsDep, info: ReqInfo) -> None:
    auth.reauthenticate(db, settings, current.session, current.user, body.password, body.code, info)
    db.commit()


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=512)
    new_password: str = Field(max_length=512)


class PasswordOut(BaseModel):
    sessions_closed: int


@router.post("/auth/password", response_model=PasswordOut)
def change_password(body: PasswordIn, current: FullAuth, db: DB, info: ReqInfo) -> PasswordOut:
    closed = auth.change_password(
        db, current.session, current.user, body.current_password, body.new_password, info
    )
    db.commit()
    return PasswordOut(sessions_closed=closed)


# --- Sesiones y dispositivos ---------------------------------------------------------------------------


class SessionOut(BaseModel):
    id: uuid.UUID
    kind: str
    device_name: str | None
    user_agent: str | None
    ip: str | None
    created_at: datetime
    last_seen_at: datetime
    current: bool


def session_out(session: AuthSession, current_id: uuid.UUID | None) -> SessionOut:
    return SessionOut(
        id=session.id,
        kind=session.kind,
        device_name=session.device_name,
        user_agent=session.user_agent,
        ip=str(session.ip) if session.ip else None,
        created_at=session.created_at,
        last_seen_at=session.last_seen_at,
        current=session.id == current_id,
    )


@router.get("/auth/sessions", response_model=list[SessionOut])
def list_sessions(current: FullAuth, db: DB) -> list[SessionOut]:
    return [session_out(s, current.session.id) for s in auth.active_sessions(db, current.user.id)]


@router.delete("/auth/sessions/{session_id}", status_code=204)
def revoke_session(session_id: uuid.UUID, current: FullAuth, db: DB, info: ReqInfo) -> None:
    session = db.get(AuthSession, session_id)
    if session is None or session.user_id != current.user.id:
        raise NotFound("Esa sesión no existe")
    auth.revoke(db, session)
    audit.record(
        db,
        "auth.session_revoked",
        actor_id=current.user.id,
        target_type="session",
        target_id=session_id,
        request=info,
    )
    db.commit()


@router.post("/auth/sessions/revoke-others", response_model=PasswordOut)
def revoke_other_sessions(current: FullAuth, db: DB, info: ReqInfo) -> PasswordOut:
    closed = auth.revoke_all(db, current.user.id, except_id=current.session.id)
    audit.record(
        db, "auth.sessions_revoked", actor_id=current.user.id, request=info, detail={"count": closed}
    )
    db.commit()
    return PasswordOut(sessions_closed=closed)


# --- Perfil (/me) --------------------------------------------------------------------------------------


class SpaceSummary(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    archived: bool


class MeOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    is_admin: bool
    stage: Stage
    has_totp: bool
    require_2fa: bool
    recovery_codes_left: int
    reauth_until: datetime
    current_space_id: uuid.UUID | None
    spaces: list[SpaceSummary]
    preferences: dict[str, object]


@router.get("/me", response_model=MeOut)
def me(current: PartialAuth, db: DB, settings: SettingsDep) -> MeOut:
    user = current.user
    full = current.session.stage == "full"
    space_list = spaces.list_for_user(db, user) if full else []
    return MeOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_admin=user.is_admin,
        stage=current.session.stage,  # type: ignore[arg-type]
        has_totp=user.has_totp,
        require_2fa=settings.require_2fa,
        recovery_codes_left=auth.remaining_recovery_codes(db, user.id) if full else 0,
        reauth_until=current.session.reauth_at + auth.REAUTH_WINDOW,
        current_space_id=spaces.default_space_id(db, user) if full else None,
        spaces=[
            SpaceSummary(
                id=a.space.id, name=a.space.name, role=a.role, archived=a.space.archived_at is not None
            )
            for a in space_list
        ],
        preferences=user.preferences if full else {},
    )


class MeIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    last_space_id: uuid.UUID | None = None
    theme: Literal["system", "light", "dark"] | None = None


@router.patch("/me", status_code=204)
def update_me(body: MeIn, current: FullAuth, db: DB) -> None:
    user = current.user
    if body.display_name is not None:
        user.display_name = invitations._validate_display_name(body.display_name)
    if body.last_space_id is not None:
        spaces.access(db, user, body.last_space_id)  # solo espacios propios
        user.last_space_id = body.last_space_id
    if body.theme is not None:
        user.preferences = {**user.preferences, "theme": body.theme}
    db.commit()
