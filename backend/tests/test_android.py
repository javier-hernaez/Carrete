"""Acceso de la app Android con token de dispositivo, sesión de la WebView y distribución del APK."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.conftest import make_client
from tests.helpers import PASSWORD, setup_admin, totp_code


def test_device_login_and_webview_session(client: TestClient, engine: Engine, settings, new_client) -> None:  # type: ignore[no-untyped-def]
    admin = setup_admin(client, engine)
    app = TestClient(client.app, base_url=settings.public_url)  # la app no envía Origin ni cookies
    login = app.post(
        "/api/v1/auth/device/login",
        json={"username": "javier", "password": PASSWORD, "device_name": "Pixel 8"},
    )
    assert login.status_code == 200 and login.json()["stage"] == "totp"
    assert "set-cookie" not in login.headers  # el token va en la respuesta, no en una cookie
    token = login.json()["token"]
    bearer = {"Authorization": f"Bearer {token}"}
    assert app.get("/api/v1/spaces", headers=bearer).json()["code"] == "totp_required"
    code = totp_code(admin.totp_secret or "", engine, "javier")
    assert app.post("/api/v1/auth/totp", json={"code": code}, headers=bearer).json() == {"stage": "full"}
    me = app.get("/api/v1/me", headers=bearer).json()
    assert me["stage"] == "full" and me["spaces"][0]["name"] == "Pareja"

    # Código de un solo uso para la WebView: se canjea por una cookie de sesión web
    web_code = app.post("/api/v1/auth/device/web-code", headers=bearer).json()["code"]
    webview = TestClient(client.app, base_url=settings.public_url, follow_redirects=False)
    exchanged = webview.get("/api/v1/auth/device/web", params={"code": web_code})
    assert exchanged.status_code == 303 and exchanged.headers["location"] == "/"
    assert exchanged.headers["set-cookie"].startswith("__Host-carrete=")
    assert webview.get("/api/v1/me").json()["username"] == "javier"
    again = TestClient(client.app, base_url=settings.public_url, follow_redirects=False).get(
        "/api/v1/auth/device/web", params={"code": web_code}
    )
    assert "set-cookie" not in again.headers  # un solo uso

    # Una sesión web normal no puede pedir códigos; el dispositivo aparece en la lista y se revoca
    assert admin.post("/api/v1/auth/device/web-code").status_code == 404
    sessions = admin.get("/api/v1/auth/sessions").json()
    device = next(s for s in sessions if s["kind"] == "device")
    assert device["device_name"] == "Pixel 8"
    assert any(s["device_name"] == "Pixel 8 (app)" for s in sessions)
    assert not any(s["kind"] == "exchange" for s in sessions)
    admin.delete(f"/api/v1/auth/sessions/{device['id']}")
    assert app.get("/api/v1/me", headers=bearer).status_code == 401


def test_device_login_rejects_bad_password(client: TestClient, engine: Engine, settings) -> None:  # type: ignore[no-untyped-def]
    setup_admin(client, engine)
    app = TestClient(client.app, base_url=settings.public_url)
    bad = app.post(
        "/api/v1/auth/device/login",
        json={"username": "javier", "password": "no es la buena", "device_name": "X"},
    )
    assert bad.status_code == 401
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM audit_log WHERE action = 'auth.login_failed'")
            ).scalar_one()
            == 1
        )


def test_exchange_codes_expire(client: TestClient, engine: Engine, settings, make_settings) -> None:  # type: ignore[no-untyped-def]
    admin = setup_admin(client, engine)
    app = TestClient(client.app, base_url=settings.public_url)
    token = app.post(
        "/api/v1/auth/device/login", json={"username": "javier", "password": PASSWORD, "device_name": "X"}
    ).json()["token"]
    bearer = {"Authorization": f"Bearer {token}"}
    app.post(
        "/api/v1/auth/totp",
        json={"code": totp_code(admin.totp_secret or "", engine, "javier")},
        headers=bearer,
    )
    web_code = app.post("/api/v1/auth/device/web-code", headers=bearer).json()["code"]
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE sessions SET expires_at = now() - interval '1 second' WHERE kind = 'exchange'")
        )
    late = TestClient(client.app, base_url=settings.public_url, follow_redirects=False).get(
        "/api/v1/auth/device/web", params={"code": web_code}
    )
    assert "set-cookie" not in late.headers


def test_apk_distribution(make_settings, engine: Engine, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html>")
    apk_dir = tmp_path / "apk"
    apk_dir.mkdir()
    settings = make_settings(static_dir=static, apk_dir=apk_dir)
    with make_client(settings, engine) as client:
        setup_admin(client, engine)
        assert client.get("/api/v1/app/android").json() == {
            "available": False,
            "version_name": None,
            "version_code": None,
            "size_bytes": None,
        }
        assert client.get("/api/v1/app/android/apk").status_code == 404
        (apk_dir / "carrete.apk").write_bytes(b"PK apk")
        (apk_dir / "carrete-apk.json").write_text(
            json.dumps({"version_code": 29123456, "version_name": "1.2.0"})
        )
        info = client.get("/api/v1/app/android").json()
        assert info == {"available": True, "version_name": "1.2.0", "version_code": 29123456, "size_bytes": 6}
        apk = client.get("/api/v1/app/android/apk")
        assert (
            apk.content == b"PK apk"
            and apk.headers["content-type"] == "application/vnd.android.package-archive"
        )
        qr = client.get("/api/v1/app/android/setup-qr")
        assert qr.headers["content-type"].startswith("image/svg+xml") and "<svg" in qr.text
        anonymous = TestClient(client.app, base_url=settings.public_url)
        assert anonymous.get("/api/v1/app/android/apk").status_code == 401
        # Ni siquiera adivinando una ruta de la web se llega al APK sin sesión
        assert b"PK apk" not in anonymous.get("/carrete.apk").content
