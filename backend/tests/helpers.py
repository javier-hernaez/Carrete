"""Utilidades para pruebas de la API: crear cuentas y espacios e iniciar sesión de punta a punta."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

PASSWORD = "una frase larga y segura"


@dataclass
class Person:
    client: TestClient
    username: str
    password: str = PASSWORD
    totp_secret: str | None = None
    recovery_codes: list[str] = field(default_factory=list)
    spaces: dict[str, str] = field(default_factory=dict)

    def get(self, url: str, **kw: object):  # type: ignore[no-untyped-def]
        return self.client.get(url, **kw)  # type: ignore[arg-type]

    def post(self, url: str, **kw: object):  # type: ignore[no-untyped-def]
        return self.client.post(url, **kw)  # type: ignore[arg-type]

    def patch(self, url: str, **kw: object):  # type: ignore[no-untyped-def]
        return self.client.patch(url, **kw)  # type: ignore[arg-type]

    def delete(self, url: str, **kw: object):  # type: ignore[no-untyped-def]
        return self.client.delete(url, **kw)  # type: ignore[arg-type]


def totp_code(secret: str, engine: Engine | None = None, username: str | None = None) -> str:
    """Código válido. Si se pasa el motor, olvida el último paso usado (evita la protección de reuso)."""
    if engine is not None and username is not None:
        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET totp_last_step = NULL WHERE username = :u"), {"u": username})
    return pyotp.TOTP(secret).at(time.time())


def enroll(person: Person, engine: Engine) -> None:
    secret = person.post("/api/v1/auth/totp/setup").json()["secret"]
    response = person.post("/api/v1/auth/totp/enable", json={"code": totp_code(secret)})
    assert response.status_code == 200, response.text
    person.totp_secret = secret
    person.recovery_codes = response.json()["recovery_codes"]


def setup_admin(
    client: TestClient, engine: Engine, *, username: str = "javier", space: str = "Pareja"
) -> Person:
    token = client.app.state.setup_token  # type: ignore[attr-defined]
    response = client.post(
        "/api/v1/setup",
        json={
            "token": token,
            "username": username,
            "display_name": username.title(),
            "password": PASSWORD,
            "space_name": space,
        },
    )
    assert response.status_code == 200, response.text
    person = Person(client, username)
    if response.json()["stage"] == "enroll":
        enroll(person, engine)
    me = person.get("/api/v1/me").json()
    person.spaces = {s["name"]: s["id"] for s in me["spaces"]}
    return person


def invite(owner: Person, space_id: str, role: str = "collaborator") -> str:
    response = owner.post(f"/api/v1/spaces/{space_id}/invitations", json={"role": role})
    assert response.status_code == 201, response.text
    return str(response.json()["url"]).rsplit("/", 1)[1]


def join(new_client: TestClient, engine: Engine, token: str, username: str) -> Person:
    response = new_client.post(
        f"/api/v1/invitations/by-token/{token}/accept",
        json={"username": username, "display_name": username.title(), "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    person = Person(new_client, username)
    if response.json()["stage"] == "enroll":
        enroll(person, engine)
    me = person.get("/api/v1/me").json()
    person.spaces = {s["name"]: s["id"] for s in me["spaces"]}
    return person


def login(person: Person, engine: Engine) -> str:
    response = person.post(
        "/api/v1/auth/login", json={"username": person.username, "password": person.password}
    )
    assert response.status_code == 200, response.text
    stage = response.json()["stage"]
    if stage == "totp":
        assert person.totp_secret
        response = person.post(
            "/api/v1/auth/totp", json={"code": totp_code(person.totp_secret, engine, person.username)}
        )
        assert response.status_code == 200, response.text
        stage = response.json()["stage"]
    return str(stage)
