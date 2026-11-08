"""Cuentas, sesiones y segundo factor."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import AuthSession, RecoveryCode, User
from app.security import crypto, passwords, ratelimit, totp
from app.services import audit
from app.services.audit import RequestInfo
from app.services.errors import Invalid, RateLimited, ReauthRequired, Unauthorized

IDLE_TIMEOUT = timedelta(days=30)
ABSOLUTE_TIMEOUT = timedelta(days=90)
DEVICE_TIMEOUT = timedelta(days=365)
PARTIAL_TIMEOUT = timedelta(minutes=15)  # sesión a medias (falta el segundo factor)
REAUTH_WINDOW = timedelta(minutes=15)
LAST_SEEN_THROTTLE = timedelta(minutes=5)

TOTP_PURPOSE = "totp-secret"
INVALID_CREDENTIALS = "Usuario o contraseña incorrectos"


def now() -> datetime:
    return datetime.now(UTC)


def normalize_username(username: str) -> str:
    return username.strip().lower()


@dataclass
class IssuedSession:
    session: AuthSession
    token: str


# --- Sesiones ------------------------------------------------------------------------------------------


def issue_session(
    db: Session,
    user: User,
    *,
    stage: str,
    request: RequestInfo,
    kind: str = "web",
    device_name: str | None = None,
) -> IssuedSession:
    token = crypto.new_token()
    lifetime = DEVICE_TIMEOUT if kind == "device" else ABSOLUTE_TIMEOUT
    if stage != "full":
        lifetime = PARTIAL_TIMEOUT
    session = AuthSession(
        user_id=user.id,
        token_hash=crypto.hash_token(token),
        kind=kind,
        stage=stage,
        device_name=device_name,
        ip=request.ip,
        user_agent=(request.user_agent or "")[:500] or None,
        expires_at=now() + lifetime,
        reauth_at=now(),
        last_seen_at=now(),
    )
    db.add(session)
    db.flush()
    return IssuedSession(session, token)


def resolve_session(db: Session, token: str | None) -> tuple[AuthSession, User] | None:
    if not token or len(token) > 200:
        return None
    row = db.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.token_hash == crypto.hash_token(token))
    ).first()
    if row is None:
        return None
    session, user = row.tuple()
    current = now()
    idle_limit = DEVICE_TIMEOUT if session.kind == "device" else IDLE_TIMEOUT
    if (
        session.revoked_at is not None
        or session.expires_at <= current
        or session.last_seen_at + idle_limit <= current
        or not user.is_active
    ):
        return None
    if current - session.last_seen_at > LAST_SEEN_THROTTLE:
        session.last_seen_at = current
        db.commit()
    return session, user


def revoke(db: Session, session: AuthSession) -> None:
    session.revoked_at = now()


def revoke_all(db: Session, user_id: uuid.UUID, *, except_id: uuid.UUID | None = None) -> int:
    stmt = (
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now())
    )
    if except_id is not None:
        stmt = stmt.where(AuthSession.id != except_id)
    return int(db.execute(stmt).rowcount)  # type: ignore[attr-defined]


def active_sessions(db: Session, user_id: uuid.UUID) -> list[AuthSession]:
    current = now()
    return list(
        db.scalars(
            select(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > current,
                AuthSession.stage == "full",
            )
            .order_by(AuthSession.last_seen_at.desc())
        )
    )


def _upgrade(session: AuthSession, stage: str = "full") -> None:
    session.stage = stage
    session.reauth_at = now()
    lifetime = DEVICE_TIMEOUT if session.kind == "device" else ABSOLUTE_TIMEOUT
    session.expires_at = now() + lifetime


def require_recent_auth(session: AuthSession) -> None:
    if now() - session.reauth_at > REAUTH_WINDOW:
        raise ReauthRequired("Por seguridad, vuelve a introducir tu contraseña")


# --- Inicio de sesión ----------------------------------------------------------------------------------


def _guard(db: Session, username: str | None, ip: str | None) -> None:
    try:
        ratelimit.check(db, username=username, ip=ip)
    except ratelimit.TooManyAttempts as exc:
        raise RateLimited(
            f"Demasiados intentos. Espera {exc.retry_after} segundos.", retry_after=exc.retry_after
        ) from exc


def _fail(db: Session, *, username: str | None, user: User | None, request: RequestInfo, why: str) -> None:
    ratelimit.record_failure(db, username=username, ip=request.ip)
    audit.record(
        db,
        "auth.login_failed",
        actor_id=user.id if user else None,
        request=request,
        detail={"username": username, "reason": why},
    )
    db.commit()


def login(
    db: Session, settings: Settings, username: str, password: str, request: RequestInfo
) -> IssuedSession:
    username = normalize_username(username)
    _guard(db, username, request.ip)
    user = db.scalar(select(User).where(User.username == username))
    valid = passwords.verify_password(user.password_hash if user else None, password)
    if user is None or not valid or not user.is_active:
        _fail(db, username=username, user=user, request=request, why="credentials")
        raise Unauthorized(INVALID_CREDENTIALS, code="invalid_credentials")

    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    if user.has_totp:
        stage = "totp"
    elif settings.require_2fa:
        stage = "enroll"
    else:
        stage = "full"
    issued = issue_session(db, user, stage=stage, request=request)
    if stage == "full":
        _logged_in(db, user, request)
    return issued


def _logged_in(db: Session, user: User, request: RequestInfo) -> None:
    user.last_login_at = now()
    ratelimit.clear(db, username=user.username)
    audit.record(db, "auth.login", actor_id=user.id, request=request)


def verify_second_factor(
    db: Session, settings: Settings, session: AuthSession, user: User, code: str, request: RequestInfo
) -> None:
    """Completa un inicio de sesión a medias con un código TOTP o de recuperación."""
    _guard(db, user.username, request.ip)
    if _check_code(db, settings, user, code, request):
        _upgrade(session)
        _logged_in(db, user, request)
        return
    _fail(db, username=user.username, user=user, request=request, why="second_factor")
    raise Unauthorized("Código incorrecto", code="invalid_code")


def _check_code(db: Session, settings: Settings, user: User, code: str, request: RequestInfo) -> bool:
    if user.totp_secret_enc is None:
        return False
    secret = crypto.decrypt(settings.secret_key.get_secret_value(), TOTP_PURPOSE, user.totp_secret_enc)
    step = totp.verify(secret.decode(), code, last_step=user.totp_last_step)
    if step is not None:
        user.totp_last_step = step
        return True
    if "-" in code or len(code.strip()) >= 10:
        recovery = db.scalar(
            select(RecoveryCode).where(
                RecoveryCode.user_id == user.id,
                RecoveryCode.used_at.is_(None),
                RecoveryCode.code_hash == totp.hash_recovery_code(code),
            )
        )
        if recovery is not None:
            recovery.used_at = now()
            left = remaining_recovery_codes(db, user.id) - 1
            audit.record(db, "auth.recovery_code_used", actor_id=user.id, request=request)
            from app.services.notices import raise_notice

            raise_notice(
                db,
                "recovery_code_used",
                f"{user.display_name} ha entrado con un código de recuperación (le quedan {left})",
                severity="info",
                detail={"user_id": str(user.id)},
            )
            return True
    return False


def remaining_recovery_codes(db: Session, user_id: uuid.UUID) -> int:
    return int(
        db.scalar(select(func.count()).where(RecoveryCode.user_id == user_id, RecoveryCode.used_at.is_(None)))
        or 0
    )


def reauthenticate(
    db: Session,
    settings: Settings,
    session: AuthSession,
    user: User,
    password: str,
    code: str | None,
    request: RequestInfo,
) -> None:
    _guard(db, user.username, request.ip)
    ok = passwords.verify_password(user.password_hash, password)
    if ok and user.has_totp:
        ok = code is not None and _check_code(db, settings, user, code, request)
    if not ok:
        _fail(db, username=user.username, user=user, request=request, why="reauth")
        raise Unauthorized("Contraseña o código incorrectos", code="invalid_credentials")
    session.reauth_at = now()
    audit.record(db, "auth.reauth", actor_id=user.id, request=request)


# --- Segundo factor ------------------------------------------------------------------------------------


def start_totp_enrollment(db: Session, settings: Settings, user: User) -> dict[str, str]:
    secret = totp.new_secret()
    user.totp_pending_enc = crypto.encrypt(
        settings.secret_key.get_secret_value(), TOTP_PURPOSE, secret.encode()
    )
    uri = totp.provisioning_uri(secret, user.username)
    return {"secret": secret, "otpauth_uri": uri, "qr_svg": totp.qr_svg(uri)}


def finish_totp_enrollment(
    db: Session, settings: Settings, session: AuthSession, user: User, code: str, request: RequestInfo
) -> list[str]:
    if user.totp_pending_enc is None:
        raise Invalid("Primero hay que generar el código QR", code="no_pending_totp")
    _guard(db, user.username, request.ip)
    secret = crypto.decrypt(settings.secret_key.get_secret_value(), TOTP_PURPOSE, user.totp_pending_enc)
    step = totp.verify(secret.decode(), code, last_step=None)
    if step is None:
        _fail(db, username=user.username, user=user, request=request, why="totp_enroll")
        raise Invalid(
            "El código no coincide. Comprueba la hora del móvil y vuelve a probar.", code="invalid_code"
        )
    user.totp_secret_enc = user.totp_pending_enc
    user.totp_pending_enc = None
    user.totp_last_step = step
    codes = replace_recovery_codes(db, user)
    was_enrolling = session.stage == "enroll"
    _upgrade(session)
    if was_enrolling:
        _logged_in(db, user, request)
    audit.record(db, "auth.totp_enabled", actor_id=user.id, request=request)
    return codes


def replace_recovery_codes(db: Session, user: User) -> list[str]:
    db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id).delete()
    codes = totp.new_recovery_codes()
    for code in codes:
        db.add(RecoveryCode(user_id=user.id, code_hash=totp.hash_recovery_code(code)))
    return codes


def disable_totp(db: Session, settings: Settings, user: User, request: RequestInfo) -> None:
    if settings.require_2fa:
        raise Invalid("El segundo factor es obligatorio en esta instancia", code="totp_required")
    user.totp_secret_enc = None
    user.totp_pending_enc = None
    user.totp_last_step = None
    db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id).delete()
    audit.record(db, "auth.totp_disabled", actor_id=user.id, request=request)


# --- Contraseñas ---------------------------------------------------------------------------------------


def set_password(user: User, password: str) -> None:
    try:
        passwords.validate(password, username=user.username)
    except passwords.WeakPasswordError as exc:
        raise Invalid(str(exc), code="weak_password") from exc
    user.password_hash = passwords.hash_password(password)
    user.password_changed_at = now()


def change_password(
    db: Session, session: AuthSession, user: User, current: str, new: str, request: RequestInfo
) -> int:
    _guard(db, user.username, request.ip)
    if not passwords.verify_password(user.password_hash, current):
        _fail(db, username=user.username, user=user, request=request, why="change_password")
        raise Unauthorized("La contraseña actual no es correcta", code="invalid_credentials")
    set_password(user, new)
    closed = revoke_all(db, user.id, except_id=session.id)
    audit.record(
        db, "auth.password_changed", actor_id=user.id, request=request, detail={"sessions_closed": closed}
    )
    return closed
