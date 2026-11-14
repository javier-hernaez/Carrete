"""Autenticador WebAuthn por software para las pruebas: genera respuestas reales firmadas con ES256."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SoftKey:
    def __init__(self, rp_id: str, origin: str) -> None:
        self.rp_id = rp_id
        self.origin = origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.count = 0
        self.user_handle: bytes | None = None

    def _cose(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps(
            {1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")}
        )

    def _client_data(self, kind: str, challenge: str, origin: str | None = None) -> bytes:
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": origin or self.origin, "crossOrigin": False}
        ).encode()

    def create(self, options: dict) -> dict:  # type: ignore[type-arg]
        self.user_handle = unb64url(options["user"]["id"])
        rp_hash = hashlib.sha256(self.rp_id.encode()).digest()
        attested = bytes(16) + struct.pack(">H", len(self.credential_id)) + self.credential_id + self._cose()
        auth_data = rp_hash + bytes([0x45]) + struct.pack(">I", self.count) + attested  # UP | UV | AT
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(self._client_data("webauthn.create", options["challenge"])),
                "attestationObject": b64url(attestation),
                "transports": ["internal"],
            },
        }

    def get(self, options: dict, *, origin: str | None = None, user_verified: bool = True) -> dict:  # type: ignore[type-arg]
        self.count += 1
        rp_hash = hashlib.sha256(self.rp_id.encode()).digest()
        auth_data = rp_hash + bytes([0x05 if user_verified else 0x01]) + struct.pack(">I", self.count)
        client = self._client_data("webauthn.get", options["challenge"], origin)
        signature = self.key.sign(auth_data + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client),
                "authenticatorData": b64url(auth_data),
                "signature": b64url(signature),
                "userHandle": b64url(self.user_handle or b""),
            },
        }
