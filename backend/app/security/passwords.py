"""Contraseñas: Argon2id, mínimo 12 caracteres, rechazo de las comunes. Sin reglas de composición ni
caducidad periódica (NIST SP 800-63B, ASVS 2.1)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 12
MAX_LENGTH = 256

# Parámetros recomendados por OWASP para Argon2id (19 MiB, 2 pasadas) un poco reforzados.
_hasher = PasswordHasher(time_cost=3, memory_cost=32 * 1024, parallelism=2)

# Hash de una contraseña cualquiera: se verifica contra él cuando el usuario no existe, para que la
# respuesta tarde lo mismo y no delate qué nombres de usuario existen.
_DUMMY_HASH = _hasher.hash("carrete-usuario-inexistente")


class WeakPasswordError(ValueError):
    pass


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    path = Path(__file__).resolve().parent.parent / "data" / "common-passwords.txt"
    return frozenset(
        line.strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )


def validate(password: str, *, username: str | None = None) -> None:
    if len(password) < MIN_LENGTH:
        raise WeakPasswordError(f"La contraseña debe tener al menos {MIN_LENGTH} caracteres")
    if len(password) > MAX_LENGTH:
        raise WeakPasswordError(f"La contraseña no puede tener más de {MAX_LENGTH} caracteres")
    lowered = password.lower()
    if lowered in _common_passwords() or len(set(lowered)) < 4:
        raise WeakPasswordError("Esa contraseña es demasiado común; elige otra")
    if username and len(username) >= 3 and username.lower() in lowered:
        raise WeakPasswordError("La contraseña no puede contener tu nombre de usuario")
    if "carrete" in lowered and len(lowered) < 20:
        raise WeakPasswordError("La contraseña no puede basarse en el nombre de la aplicación")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
