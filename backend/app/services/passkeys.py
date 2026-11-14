"""Llaves de acceso (passkeys, WebAuthn): alternativa a contraseña + TOTP.

Una llave con verificación del usuario (huella, cara o PIN del dispositivo) ya combina dos factores
(algo que se tiene y algo que se es o se sabe), así que da una sesión completa directamente.

Nota: WebAuthn liga las llaves al nombre de equipo, no al puerto. Las otras aplicaciones
del mismo nombre podrían pedir una firma con la llave de Carrete, pero el navegador siempre muestra el
diálogo y la firma solo sirve con un reto emitido por Carrete y para el origen exacto (con puerto).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import Settings
from app.db.models import User, WebauthnChallenge, WebauthnCredential
from app.services import audit, auth
from app.services.audit import RequestInfo
from app.services.errors import Invalid, NotFound, Unauthorized

CHALLENGE_TTL = timedelta(minutes=5)


def rp_id(settings: Settings) -> str:
    return urlsplit(settings.public_url).hostname or "localhost"


def _store_challenge(
    db: Session, purpose: str, challenge: bytes, user_id: uuid.UUID | None
) -> WebauthnChallenge:
    db.execute(delete(WebauthnChallenge).where(WebauthnChallenge.expires_at < datetime.now(UTC)))
    record = WebauthnChallenge(
        purpose=purpose, challenge=challenge, user_id=user_id, expires_at=datetime.now(UTC) + CHALLENGE_TTL
    )
    db.add(record)
    db.flush()
    return record


def _take_challenge(db: Session, challenge_id: uuid.UUID, purpose: str, user_id: uuid.UUID | None) -> bytes:
    record = db.get(WebauthnChallenge, challenge_id)
    if (
        record is None
        or record.purpose != purpose
        or record.expires_at < datetime.now(UTC)
        or record.user_id != user_id
    ):
        raise Invalid("El reto ha caducado; vuelve a intentarlo", code="challenge_expired")
    challenge = record.challenge
    db.delete(record)  # un solo uso
    return challenge


def registration_options(db: Session, settings: Settings, user: User) -> dict[str, Any]:
    existing = db.scalars(
        select(WebauthnCredential.credential_id).where(WebauthnCredential.user_id == user.id)
    )
    options = generate_registration_options(
        rp_id=rp_id(settings),
        rp_name="Carrete",
        user_name=user.username,
        user_id=user.id.bytes,
        user_display_name=user.display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=c) for c in existing],
    )
    record = _store_challenge(db, "register", options.challenge, user.id)
    return {"challenge_id": str(record.id), "options": json.loads(options_to_json(options))}


def register(
    db: Session,
    settings: Settings,
    user: User,
    challenge_id: uuid.UUID,
    credential: dict[str, Any],
    name: str,
    request: RequestInfo,
) -> WebauthnCredential:
    challenge = _take_challenge(db, challenge_id, "register", user.id)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id(settings),
            expected_origin=settings.public_origin,
            require_user_verification=True,
        )
    except InvalidRegistrationResponse as exc:
        raise Invalid(f"No se pudo registrar la llave: {exc}", code="invalid_passkey") from exc
    record = WebauthnCredential(
        user_id=user.id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        name=(name.strip() or "Llave de acceso")[:80],
        transports=[t for t in credential.get("response", {}).get("transports", []) if isinstance(t, str)][
            :8
        ],
    )
    db.add(record)
    db.flush()
    audit.record(db, "auth.passkey_added", actor_id=user.id, request=request, detail={"name": record.name})
    return record


def login_options(db: Session, settings: Settings) -> dict[str, Any]:
    # Llaves «descubribles»: el navegador ofrece las que tenga, sin decir antes qué usuarios existen.
    options = generate_authentication_options(
        rp_id=rp_id(settings), user_verification=UserVerificationRequirement.REQUIRED
    )
    record = _store_challenge(db, "login", options.challenge, None)
    return {"challenge_id": str(record.id), "options": json.loads(options_to_json(options))}


def login(
    db: Session, settings: Settings, challenge_id: uuid.UUID, credential: dict[str, Any], request: RequestInfo
) -> auth.IssuedSession:
    auth._guard(db, None, request.ip)
    challenge = _take_challenge(db, challenge_id, "login", None)
    try:
        raw_id = base64url_to_bytes(str(credential.get("rawId") or credential.get("id") or ""))
    except (ValueError, TypeError) as exc:
        raise Unauthorized("Llave no reconocida", code="invalid_passkey") from exc
    stored = db.scalar(select(WebauthnCredential).where(WebauthnCredential.credential_id == raw_id))
    user = db.get(User, stored.user_id) if stored else None
    if stored is None or user is None or not user.is_active:
        auth._fail(db, username=None, user=None, request=request, why="passkey_unknown")
        raise Unauthorized("Llave no reconocida", code="invalid_passkey")
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id(settings),
            expected_origin=settings.public_origin,
            credential_public_key=stored.public_key,
            credential_current_sign_count=stored.sign_count,
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as exc:
        auth._fail(db, username=user.username, user=user, request=request, why="passkey_invalid")
        raise Unauthorized("La llave no es válida", code="invalid_passkey") from exc
    stored.sign_count = verified.new_sign_count
    stored.last_used_at = datetime.now(UTC)
    issued = auth.issue_session(db, user, stage="full", request=request)
    auth._logged_in(db, user, request)
    return issued


def list_for(db: Session, user: User) -> list[WebauthnCredential]:
    return list(
        db.scalars(
            select(WebauthnCredential)
            .where(WebauthnCredential.user_id == user.id)
            .order_by(WebauthnCredential.created_at)
        )
    )


def remove(db: Session, user: User, credential_id: uuid.UUID, request: RequestInfo) -> None:
    record = db.get(WebauthnCredential, credential_id)
    if record is None or record.user_id != user.id:
        raise NotFound("Esa llave no existe")
    db.delete(record)
    audit.record(db, "auth.passkey_removed", actor_id=user.id, request=request, detail={"name": record.name})
