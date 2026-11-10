"""Criptografía de la aplicación (A.8.24).

- Secretos en reposo (p. ej. TOTP): AES-256-GCM con una clave derivada de ``CARRETE_SECRET_KEY`` por
  HKDF-SHA256, distinta para cada propósito. Formato: versión (1 byte) · nonce (12) · cifrado+etiqueta.
- *Tokens* (sesiones, invitaciones, dispositivos): 256 bits aleatorios; en la base de datos solo se
  guarda su SHA-256, así que un volcado robado no permite suplantar a nadie.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_VERSION = b"\x01"


def derive_key(master: str, purpose: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"carrete-v1", info=purpose.encode()).derive(
        master.encode()
    )


def encrypt(master: str, purpose: str, plaintext: bytes) -> bytes:
    nonce = os.urandom(12)
    sealed = AESGCM(derive_key(master, purpose)).encrypt(nonce, plaintext, purpose.encode())
    return _VERSION + nonce + sealed


def decrypt(master: str, purpose: str, blob: bytes) -> bytes:
    if not blob or blob[:1] != _VERSION:
        raise ValueError("Formato de secreto desconocido")
    nonce, sealed = blob[1:13], blob[13:]
    return AESGCM(derive_key(master, purpose)).decrypt(nonce, sealed, purpose.encode())


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
