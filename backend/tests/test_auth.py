"""Acceso: asistente inicial, inicio de sesión, segundo factor, límites, sesiones y CSRF."""

from __future__ import annotations

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.helpers import PASSWORD, Person, login, setup_admin, totp_code


def test_setup_wizard_flow(client: TestClient, engine: Engine) -> None:
    assert client.get("/api/v1/setup").json() == {"needed": True}
    bad = client.post(
        "/api/v1/setup",
        json={
            "token": "no",
            "username": "javier",
            "display_name": "J",
            "password": PASSWORD,
            "space_name": "P",
        },
    )
    assert bad.status_code == 403 and bad.json()["code"] == "invalid_setup_token"

    token = client.app.state.setup_token  # type: ignore[attr-defined]
    response = client.post(
        "/api/v1/setup",
        json={
            "token": token,
            "username": "Javier",
            "display_name": "Javier",
            "password": PASSWORD,
            "space_name": "Pareja",
        },
    )
    assert response.json() == {"stage": "enroll"}
    # Sin segundo factor no se puede hacer nada más
    blocked = client.get("/api/v1/spaces")
    assert blocked.status_code == 401 and blocked.json()["code"] == "enroll_required"
    assert client.get("/api/v1/me").json()["stage"] == "enroll"

    setup = client.post("/api/v1/auth/totp/setup").json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/Carrete:javier")
    assert "<svg" in setup["qr_svg"]
    wrong = client.post("/api/v1/auth/totp/enable", json={"code": "000000"})
    assert wrong.status_code == 422
    enabled = client.post("/api/v1/auth/totp/enable", json={"code": pyotp.TOTP(setup["secret"]).now()})
    assert len(enabled.json()["recovery_codes"]) == 10

    me = client.get("/api/v1/me").json()
    assert me["stage"] == "full" and me["is_admin"] and me["username"] == "javier"
    assert [s["name"] for s in me["spaces"]] == ["Pareja"]
    assert me["current_space_id"] == me["spaces"][0]["id"]

    # El asistente se desactiva para siempre
    assert client.get("/api/v1/setup").json() == {"needed": False}
    again = client.post(
        "/api/v1/setup",
        json={
            "token": token,
            "username": "otro",
            "display_name": "O",
            "password": PASSWORD,
            "space_name": "X",
        },
    )
    assert again.status_code == 404


def test_session_cookie_attributes(client: TestClient, engine: Engine) -> None:
    token = client.app.state.setup_token  # type: ignore[attr-defined]
    response = client.post(
        "/api/v1/setup",
        json={
            "token": token,
            "username": "javier",
            "display_name": "J",
            "password": PASSWORD,
            "space_name": "P",
        },
    )
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-carrete=")
    for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert attribute.lower() in cookie.lower()
    assert "domain" not in cookie.lower()


def test_login_with_totp_and_recovery_code(client: TestClient, engine: Engine) -> None:
    admin = setup_admin(client, engine)
    assert admin.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/me").status_code == 401

    step = admin.post("/api/v1/auth/login", json={"username": "JAVIER", "password": PASSWORD})
    assert step.json() == {"stage": "totp"}
    assert client.get("/api/v1/spaces").json()["code"] == "totp_required"
    assert admin.post("/api/v1/auth/totp", json={"code": "123456"}).status_code == 401
    ok = admin.post("/api/v1/auth/totp", json={"code": totp_code(admin.totp_secret or "", engine, "javier")})
    assert ok.json() == {"stage": "full"}

    # Un código TOTP ya usado no vale otra vez
    admin.post("/api/v1/auth/logout")
    admin.post("/api/v1/auth/login", json={"username": "javier", "password": PASSWORD})
    reused = admin.post("/api/v1/auth/totp", json={"code": pyotp.TOTP(admin.totp_secret or "").now()})
    assert reused.status_code == 401

    # Código de recuperación: vale una sola vez
    code = admin.recovery_codes[0]
    assert admin.post("/api/v1/auth/totp", json={"code": code.upper()}).json() == {"stage": "full"}
    assert client.get("/api/v1/me").json()["recovery_codes_left"] == 9
    admin.post("/api/v1/auth/logout")
    admin.post("/api/v1/auth/login", json={"username": "javier", "password": PASSWORD})
    assert admin.post("/api/v1/auth/totp", json={"code": code}).status_code == 401


def test_same_answer_for_unknown_user_and_bad_password(client: TestClient, engine: Engine) -> None:
    setup_admin(client, engine)
    client.post("/api/v1/auth/logout")
    unknown = client.post("/api/v1/auth/login", json={"username": "nadie", "password": PASSWORD})
    wrong = client.post(
        "/api/v1/auth/login", json={"username": "javier", "password": "otra contraseña larga"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_rate_limit_without_permanent_lockout(client: TestClient, engine: Engine) -> None:
    setup_admin(client, engine)
    client.post("/api/v1/auth/logout")
    for _ in range(5):
        assert (
            client.post("/api/v1/auth/login", json={"username": "javier", "password": "x" * 12}).status_code
            == 401
        )
    limited = client.post("/api/v1/auth/login", json={"username": "javier", "password": PASSWORD})
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
    # Pasada la espera se puede volver a entrar
    with engine.begin() as conn:
        conn.execute(text("UPDATE auth_failures SET at = at - interval '1 hour'"))
    assert (
        client.post("/api/v1/auth/login", json={"username": "javier", "password": PASSWORD}).status_code
        == 200
    )


def test_csrf_protection(client: TestClient, engine: Engine, settings) -> None:  # type: ignore[no-untyped-def]
    setup_admin(client, engine)
    body = {"name": "Familia"}
    no_header = client.post("/api/v1/spaces", json=body, headers={"X-Carrete-Request": ""})
    assert no_header.status_code == 403 and no_header.json()["code"] == "csrf"
    # Otra aplicación del mismo equipo (otro puerto) no puede hacer peticiones en nombre del usuario
    other_port = client.post(
        "/api/v1/spaces", json=body, headers={"Origin": "https://carrete.example.ts.net:8443"}
    )
    assert other_port.status_code == 403
    no_origin = TestClient(client.app, base_url=settings.public_url, cookies=client.cookies)
    assert no_origin.post("/api/v1/spaces", json=body, headers={"X-Carrete-Request": "1"}).status_code == 403
    assert client.post("/api/v1/spaces", json=body).status_code == 201
    # Las lecturas no necesitan cabecera
    assert no_origin.get("/api/v1/setup").status_code == 200


def test_password_change_closes_other_sessions(client: TestClient, engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    admin = setup_admin(client, engine)
    other = Person(new_client(), "javier", totp_secret=admin.totp_secret)
    assert login(other, engine) == "full"
    sessions = admin.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1

    weak = admin.post("/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "corta"})
    assert weak.status_code == 422 and weak.json()["code"] == "weak_password"
    common = admin.post(
        "/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "password1234"}
    )
    assert common.json()["code"] == "weak_password"
    bad = admin.post(
        "/api/v1/auth/password",
        json={"current_password": "mala contraseña 1", "new_password": "nueva frase muy segura"},
    )
    assert bad.status_code == 401
    ok = admin.post(
        "/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "nueva frase muy segura"}
    )
    assert ok.json() == {"sessions_closed": 1}
    assert other.get("/api/v1/me").status_code == 401
    assert admin.get("/api/v1/me").status_code == 200


def test_revoke_session(client: TestClient, engine: Engine, new_client) -> None:  # type: ignore[no-untyped-def]
    admin = setup_admin(client, engine)
    other = Person(new_client(), "javier", totp_secret=admin.totp_secret)
    login(other, engine)
    target = next(s for s in admin.get("/api/v1/auth/sessions").json() if not s["current"])
    assert admin.delete(f"/api/v1/auth/sessions/{target['id']}").status_code == 204
    assert other.get("/api/v1/me").status_code == 401
    assert admin.post("/api/v1/auth/sessions/revoke-others").json() == {"sessions_closed": 0}


def test_sensitive_actions_need_recent_auth(client: TestClient, engine: Engine) -> None:
    admin = setup_admin(client, engine)
    assert admin.post("/api/v1/auth/recovery-codes").status_code == 200
    with engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET reauth_at = now() - interval '1 hour'"))
    stale = admin.post("/api/v1/auth/recovery-codes")
    assert stale.status_code == 403 and stale.json()["code"] == "reauth_required"
    assert (
        admin.post("/api/v1/auth/reauth", json={"password": PASSWORD}).status_code == 401
    )  # falta el código
    code = totp_code(admin.totp_secret or "", engine, "javier")
    assert admin.post("/api/v1/auth/reauth", json={"password": PASSWORD, "code": code}).status_code == 204
    assert len(admin.post("/api/v1/auth/recovery-codes").json()["recovery_codes"]) == 10


def test_sessions_expire(client: TestClient, engine: Engine) -> None:
    admin = setup_admin(client, engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET last_seen_at = now() - interval '31 days'"))
    assert admin.get("/api/v1/me").status_code == 401


def test_optional_2fa(make_settings, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import make_client

    settings = make_settings(require_2fa=False)
    with make_client(settings, engine) as client:
        token = client.app.state.setup_token  # type: ignore[attr-defined]
        response = client.post(
            "/api/v1/setup",
            json={
                "token": token,
                "username": "ana",
                "display_name": "Ana",
                "password": PASSWORD,
                "space_name": "P",
            },
        )
        assert response.json() == {"stage": "full"}
        assert client.get("/api/v1/me").json()["has_totp"] is False
        assert client.post("/api/v1/auth/totp/disable").status_code == 204


def test_profile_update(client: TestClient, engine: Engine) -> None:
    admin = setup_admin(client, engine)
    other_space = admin.post("/api/v1/spaces", json={"name": "Familia"}).json()["id"]
    assert (
        admin.patch(
            "/api/v1/me", json={"display_name": " Javi ", "theme": "dark", "last_space_id": other_space}
        ).status_code
        == 204
    )
    me = admin.get("/api/v1/me").json()
    assert me["display_name"] == "Javi" and me["preferences"] == {"theme": "dark"}
    assert me["current_space_id"] == other_space
