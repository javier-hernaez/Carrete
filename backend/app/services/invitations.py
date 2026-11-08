"""Invitaciones de un solo uso, restablecimiento de acceso y asistente inicial."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Invitation, RecoveryCode, Space, User
from app.security import crypto
from app.services import audit, auth, spaces
from app.services.audit import RequestInfo
from app.services.errors import Conflict, Forbidden, Invalid, NotFound

INVITE_TTL = timedelta(days=7)
RESET_TTL = timedelta(days=2)
SETUP_LOCK = 0x6361727265746502


@dataclass
class CreatedLink:
    invitation: Invitation
    token: str

    def url(self, settings: Settings) -> str:
        path = "invitacion" if self.invitation.kind == "invite" else "restablecer"
        return f"{settings.public_url}/{path}/{self.token}"


def _validate_username(db: Session, username: str) -> str:
    username = auth.normalize_username(username)
    if not (3 <= len(username) <= 32) or not all(ch.isalnum() or ch in "._-" for ch in username):
        raise Invalid(
            "El usuario debe tener entre 3 y 32 letras, números, puntos, guiones o guiones bajos",
            code="invalid_username",
        )
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise Conflict("Ese nombre de usuario ya existe", code="username_taken")
    return username


def _validate_display_name(name: str) -> str:
    name = " ".join(name.split())
    if not (1 <= len(name) <= 60):
        raise Invalid("El nombre debe tener entre 1 y 60 caracteres", code="invalid_display_name")
    return name


def create_user(
    db: Session, username: str, display_name: str, password: str, *, is_admin: bool = False
) -> User:
    user = User(
        username=_validate_username(db, username),
        display_name=_validate_display_name(display_name),
        password_hash="!",  # noqa: S106  # nosec B106  # marcador
        is_admin=is_admin,
    )
    auth.set_password(user, password)
    db.add(user)
    db.flush()
    return user


# --- Asistente inicial ---------------------------------------------------------------------------------


def setup_needed(db: Session) -> bool:
    return not db.scalar(select(func.count()).select_from(User))


def run_setup(
    db: Session,
    settings: Settings,
    *,
    expected_token: str,
    token: str,
    username: str,
    display_name: str,
    password: str,
    space_name: str,
    request: RequestInfo,
) -> auth.IssuedSession:
    # Bloqueo de transacción: dos peticiones simultáneas no pueden crear dos administradores.
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": SETUP_LOCK})
    if not setup_needed(db):
        raise NotFound("La instalación ya está hecha")
    if not crypto.tokens_equal(token.strip(), expected_token):
        auth._fail(db, username=None, user=None, request=request, why="setup_token")
        raise Forbidden("El código de arranque no es correcto", code="invalid_setup_token")
    user = create_user(db, username, display_name, password, is_admin=True)
    spaces.create(db, user, space_name, request)
    audit.record(db, "setup.completed", actor_id=user.id, request=request)
    stage = "enroll" if settings.require_2fa else "full"
    return auth.issue_session(db, user, stage=stage, request=request)


# --- Invitaciones --------------------------------------------------------------------------------------


def create_invitation(
    db: Session, actor: User, space_id: uuid.UUID | None, role: str | None, request: RequestInfo
) -> CreatedLink:
    if space_id is None:
        if not actor.is_admin:
            raise Forbidden("Solo el administrador puede invitar sin espacio")
        role = None
    else:
        spaces.access(db, actor, space_id, "owner")
        if role not in spaces.RANK:
            raise Invalid("Rol desconocido", code="invalid_role")
    token = crypto.new_token()
    invitation = Invitation(
        token_hash=crypto.hash_token(token),
        kind="invite",
        space_id=space_id,
        role=role,
        created_by=actor.id,
        expires_at=datetime.now(UTC) + INVITE_TTL,
    )
    db.add(invitation)
    db.flush()
    audit.record(
        db,
        "invitation.created",
        actor_id=actor.id,
        space_id=space_id,
        target_type="invitation",
        target_id=invitation.id,
        request=request,
        detail={"role": role},
    )
    return CreatedLink(invitation, token)


def _usable(db: Session, token: str, kind: str) -> Invitation:
    invitation = db.scalar(
        select(Invitation).where(Invitation.token_hash == crypto.hash_token(token), Invitation.kind == kind)
    )
    if (
        invitation is None
        or invitation.used_at is not None
        or invitation.revoked_at is not None
        or invitation.expires_at <= datetime.now(UTC)
    ):
        raise NotFound("Este enlace no es válido o ha caducado. Pide uno nuevo.", code="invalid_link")
    return invitation


def preview(db: Session, token: str) -> dict[str, object]:
    invitation = _usable(db, token, "invite")
    space_name = None
    if invitation.space_id is not None:
        space_name = db.scalar(select(Space.name).where(Space.id == invitation.space_id))
    inviter = db.scalar(select(User.display_name).where(User.id == invitation.created_by))
    return {
        "space_name": space_name,
        "role": invitation.role,
        "invited_by": inviter,
        "expires_at": invitation.expires_at,
    }


def accept_as_new_user(
    db: Session,
    settings: Settings,
    token: str,
    *,
    username: str,
    display_name: str,
    password: str,
    request: RequestInfo,
) -> tuple[auth.IssuedSession, uuid.UUID | None]:
    invitation = _usable(db, token, "invite")
    user = create_user(db, username, display_name, password)
    _consume(db, invitation, user, request)
    stage = "enroll" if settings.require_2fa else "full"
    return auth.issue_session(db, user, stage=stage, request=request), invitation.space_id


def accept_as_existing_user(db: Session, token: str, user: User, request: RequestInfo) -> uuid.UUID | None:
    invitation = _usable(db, token, "invite")
    _consume(db, invitation, user, request)
    return invitation.space_id


def _consume(db: Session, invitation: Invitation, user: User, request: RequestInfo) -> None:
    invitation.used_at = datetime.now(UTC)
    invitation.used_by = user.id
    if invitation.space_id is not None and invitation.role is not None:
        spaces.add_member(db, invitation.space_id, user.id, invitation.role)
        user.last_space_id = invitation.space_id
    audit.record(
        db,
        "invitation.accepted",
        actor_id=user.id,
        space_id=invitation.space_id,
        target_type="invitation",
        target_id=invitation.id,
        request=request,
    )


def pending_invitations(db: Session, space_id: uuid.UUID) -> list[Invitation]:
    return list(
        db.scalars(
            select(Invitation)
            .where(
                Invitation.space_id == space_id,
                Invitation.kind == "invite",
                Invitation.used_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.expires_at > datetime.now(UTC),
            )
            .order_by(Invitation.created_at.desc())
        )
    )


def revoke_invitation(db: Session, actor: User, invitation_id: uuid.UUID, request: RequestInfo) -> None:
    invitation = db.get(Invitation, invitation_id)
    if invitation is None or invitation.kind != "invite":
        raise NotFound("Esa invitación no existe")
    if invitation.space_id is not None:
        spaces.access(db, actor, invitation.space_id, "owner")
    elif not actor.is_admin:
        raise NotFound("Esa invitación no existe")
    invitation.revoked_at = datetime.now(UTC)
    audit.record(
        db,
        "invitation.revoked",
        actor_id=actor.id,
        space_id=invitation.space_id,
        target_id=invitation.id,
        request=request,
    )


# --- Restablecer acceso --------------------------------------------------------------------------------


def create_reset(
    db: Session, admin: User, target: User, *, reset_totp: bool, request: RequestInfo
) -> CreatedLink:
    token = crypto.new_token()
    invitation = Invitation(
        token_hash=crypto.hash_token(token),
        kind="reset",
        target_user_id=target.id,
        reset_totp=reset_totp,
        created_by=admin.id,
        expires_at=datetime.now(UTC) + RESET_TTL,
    )
    db.add(invitation)
    db.flush()
    audit.record(
        db,
        "user.reset_link_created",
        actor_id=admin.id,
        target_type="user",
        target_id=target.id,
        request=request,
        detail={"reset_totp": reset_totp},
    )
    return CreatedLink(invitation, token)


def reset_preview(db: Session, token: str) -> dict[str, object]:
    invitation = _usable(db, token, "reset")
    user = db.get(User, invitation.target_user_id)
    return {"username": user.username if user else None, "reset_totp": invitation.reset_totp}


def use_reset(db: Session, token: str, password: str, request: RequestInfo) -> None:
    invitation = _usable(db, token, "reset")
    user = db.get(User, invitation.target_user_id)
    if user is None:
        raise NotFound("Este enlace no es válido o ha caducado. Pide uno nuevo.", code="invalid_link")
    auth.set_password(user, password)
    if invitation.reset_totp:
        user.totp_secret_enc = None
        user.totp_pending_enc = None
        user.totp_last_step = None
        db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id).delete()
    invitation.used_at = datetime.now(UTC)
    invitation.used_by = user.id
    auth.revoke_all(db, user.id)
    audit.record(
        db,
        "user.access_reset",
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
        request=request,
        detail={"reset_totp": invitation.reset_totp},
    )
