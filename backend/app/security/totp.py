"""Segundo factor TOTP (RFC 6238) y códigos de recuperación."""

from __future__ import annotations

import hashlib
import secrets
import time

import pyotp
import segno
from pyotp.totp import TOTP

ISSUER = "Carrete"
RECOVERY_CODES = 10
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # sin caracteres confundibles (l/1, o/0, i)


def new_secret() -> str:
    return pyotp.random_base32(length=32)


def provisioning_uri(secret: str, username: str, issuer: str = ISSUER) -> str:
    return TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def qr_svg(uri: str) -> str:
    return str(segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#1c1916", light="#ffffff"))


def verify(secret: str, code: str, *, last_step: int | None, now: float | None = None) -> int | None:
    """Comprueba el código (±1 intervalo de 30 s). Devuelve el paso usado, o None si no vale.

    Un paso ya usado no se acepta otra vez: un código interceptado no sirve para un segundo inicio.
    """
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != 6:
        return None
    totp = TOTP(secret)
    current = int((now if now is not None else time.time()) // 30)
    for step in (current - 1, current, current + 1):
        if last_step is not None and step <= last_step:
            continue
        if secrets.compare_digest(totp.generate_otp(step), code):
            return step
    return None


def new_recovery_codes() -> list[str]:
    def one() -> str:
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(10))
        return f"{raw[:5]}-{raw[5:]}"

    return [one() for _ in range(RECOVERY_CODES)]


def normalize_recovery_code(code: str) -> str:
    raw = "".join(ch for ch in code.lower() if ch.isalnum())
    return f"{raw[:5]}-{raw[5:]}"


def hash_recovery_code(code: str) -> str:
    # 50 bits de entropía, de un solo uso: basta SHA-256 (no es una contraseña elegida por una persona).
    return hashlib.sha256(normalize_recovery_code(code).encode()).hexdigest()
