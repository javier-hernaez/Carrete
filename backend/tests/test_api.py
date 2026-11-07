from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.config import Settings
from app.main import create_app


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_ok(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200, response.text
    assert response.json()["checks"] == {"database": "ok", "schema": "ok", "data_dir": "ok"}


def test_readyz_fails_without_database(settings: Settings) -> None:
    engine = create_engine("postgresql+psycopg://x:y@127.0.0.1:1/nada", connect_args={"connect_timeout": 1})
    with TestClient(create_app(settings, engine)) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "fail"
    assert response.json()["checks"]["schema"] == "fail"


def test_readyz_fails_with_pending_migrations(settings: Settings, empty_engine) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(settings, empty_engine)) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "ok", "schema": "fail", "data_dir": "ok"}


def test_readyz_fails_without_data_dir(make_settings, engine, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(data_dir=tmp_path / "no-existe")
    with TestClient(create_app(settings, engine)) as client:
        assert client.get("/readyz").json()["checks"]["data_dir"] == "fail"


@pytest.fixture
def offline_client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings, MagicMock()))


def test_security_headers(offline_client: TestClient) -> None:
    headers = offline_client.get("/healthz").headers
    csp = headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "same-origin"
    assert headers["strict-transport-security"].startswith("max-age=")
    assert "camera=()" in headers["permissions-policy"]
    assert "server" not in headers


def test_no_hsts_over_plain_http(make_settings) -> None:  # type: ignore[no-untyped-def]
    client = TestClient(create_app(make_settings(public_url="http://127.0.0.1:8010"), MagicMock()))
    assert "strict-transport-security" not in client.get("/healthz").headers


def test_map_provider_is_allowed_in_csp(make_settings) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(map_style_url="https://tiles.openfreemap.org/styles/liberty")
    client = TestClient(create_app(settings, MagicMock()))
    csp = client.get("/healthz").headers["content-security-policy"]
    assert "connect-src 'self' https://tiles.openfreemap.org" in csp
    assert client.get("/api/v1/info").json()["map_enabled"] is True


def test_request_id_is_generated_or_propagated(offline_client: TestClient) -> None:
    generated = offline_client.get("/healthz").headers["x-request-id"]
    assert len(generated) == 16
    echoed = offline_client.get("/healthz", headers={"x-request-id": "abc12345-xyz"})
    assert echoed.headers["x-request-id"] == "abc12345-xyz"
    sanitized = offline_client.get("/healthz", headers={"x-request-id": "<script>"})
    assert sanitized.headers["x-request-id"] != "<script>"


def test_unknown_api_route_is_problem_json(offline_client: TestClient) -> None:
    response = offline_client.get("/api/v1/no-existe")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == 404
    assert body["request_id"] == response.headers["x-request-id"]


def test_instance_info(offline_client: TestClient) -> None:
    body = offline_client.get("/api/v1/info").json()
    assert body["name"] == "Carrete"
    assert body["map_enabled"] is False


def test_unhandled_errors_do_not_leak(settings: Settings) -> None:
    app = create_app(settings, MagicMock())

    @app.get("/api/v1/explota")
    def explode() -> None:
        raise RuntimeError("detalle interno secreto")

    app.router.routes.insert(0, app.router.routes.pop())  # antes del comodín de /api

    response = TestClient(app, raise_server_exceptions=False).get("/api/v1/explota")
    assert response.status_code == 500
    assert "secreto" not in response.text
    assert response.headers["content-type"] == "application/problem+json"


def test_docs_hidden_in_production(make_settings) -> None:  # type: ignore[no-untyped-def]
    client = TestClient(create_app(make_settings(environment="production"), MagicMock()))
    assert client.get("/api/openapi.json").status_code == 404
    assert client.get("/api/docs").status_code == 404


class TestWeb:
    @pytest.fixture
    def web_client(self, make_settings, tmp_path: Path) -> TestClient:  # type: ignore[no-untyped-def]
        static = tmp_path / "static"
        (static / "assets").mkdir(parents=True)
        (static / "index.html").write_text("<!doctype html><title>Carrete</title>")
        (static / "assets" / "app-abc123.js").write_text("console.log(1)")
        (static / "manifest.webmanifest").write_text("{}")
        (tmp_path / "secreto.txt").write_text("no")
        return TestClient(create_app(make_settings(static_dir=static), MagicMock()))

    def test_spa_fallback(self, web_client: TestClient) -> None:
        for path in ("/", "/fotos", "/revisar/123"):
            response = web_client.get(path)
            assert response.status_code == 200
            assert "Carrete" in response.text
            assert response.headers["cache-control"] == "no-cache"

    def test_hashed_assets_are_immutable(self, web_client: TestClient) -> None:
        response = web_client.get("/assets/app-abc123.js")
        assert response.status_code == 200
        assert "immutable" in response.headers["cache-control"]
        assert web_client.get("/assets/no-existe.js").status_code == 404

    def test_head_requests(self, web_client: TestClient) -> None:
        assert web_client.head("/").status_code == 200
        assert web_client.head("/fotos").status_code == 200

    def test_root_files(self, web_client: TestClient) -> None:
        assert web_client.get("/manifest.webmanifest").text == "{}"

    def test_no_path_traversal(self, web_client: TestClient) -> None:
        response = web_client.get("/..%2Fsecreto.txt")
        assert response.text != "no"
        assert "Carrete" in response.text

    def test_api_paths_never_return_html(self, web_client: TestClient) -> None:
        assert web_client.get("/api/v1/nada").headers["content-type"] == "application/problem+json"
