from __future__ import annotations

import ipaddress

import pytest
from pydantic import ValidationError

from app.config import Settings, describe_errors

BASE = {
    "database_url": "postgresql+psycopg://u:p@db/carrete",
    "secret_key": "s3cr3t-" + "abcdefghijklmnopqrstuvwxyz0123456789",
    "public_url": "https://equipo.tailnet.ts.net:10000",
}


def build(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for key in [*BASE, "environment", "trusted_proxies", "map_style_url"]:
        monkeypatch.delenv(f"CARRETE_{key.upper()}", raising=False)
    for key, value in {**BASE, **env}.items():
        monkeypatch.setenv(f"CARRETE_{key.upper()}", value)
    return Settings()  # type: ignore[call-arg]


def test_valid_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = build(monkeypatch)
    assert settings.environment == "production"
    assert settings.require_2fa is True
    assert settings.public_origin == "https://equipo.tailnet.ts.net:10000"
    assert settings.is_https
    assert ipaddress.ip_network("172.16.0.0/12") in settings.trusted_proxies


def test_trailing_slash_is_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    assert build(monkeypatch, public_url="https://a.b:10000/").public_url == "https://a.b:10000"


def test_trusted_proxies_are_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = build(monkeypatch, trusted_proxies="10.0.0.1, 192.168.0.0/16")
    assert settings.trusted_proxies == [
        ipaddress.ip_network("10.0.0.1/32"),
        ipaddress.ip_network("192.168.0.0/16"),
    ]


@pytest.mark.parametrize(
    ("env", "variable", "fragment"),
    [
        ({"secret_key": "corta"}, "CARRETE_SECRET_KEY", "32 caracteres"),
        ({"secret_key": "a" * 40}, "CARRETE_SECRET_KEY", "aleatoria"),
        ({"database_url": "mysql://u@h/d"}, "CARRETE_DATABASE_URL", "PostgreSQL"),
        ({"public_url": "equipo:10000"}, "CARRETE_PUBLIC_URL", "http"),
        ({"trusted_proxies": "no-es-una-ip"}, "CARRETE_TRUSTED_PROXIES", "no es una IP"),
    ],
)
def test_invalid_values_name_the_variable(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], variable: str, fragment: str
) -> None:
    with pytest.raises(ValidationError) as info:
        build(monkeypatch, **env)
    lines = describe_errors(info.value)
    assert any(line.startswith(variable) and fragment in line for line in lines), lines


def test_missing_values_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in BASE:
        monkeypatch.delenv(f"CARRETE_{key.upper()}", raising=False)
    with pytest.raises(ValidationError) as info:
        Settings()  # type: ignore[call-arg]
    lines = describe_errors(info.value)
    assert {line.split(":")[0] for line in lines} == {
        "CARRETE_DATABASE_URL",
        "CARRETE_SECRET_KEY",
        "CARRETE_PUBLIC_URL",
    }
    assert all("falta" in line for line in lines)


def test_production_requires_https_except_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="https"):
        build(monkeypatch, public_url="http://equipo.tailnet.ts.net:10000")
    assert build(monkeypatch, public_url="http://127.0.0.1:8010").is_https is False
    assert build(monkeypatch, environment="development", public_url="http://dev.lan:8010")


def test_public_url_without_path(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="ruta"):
        build(monkeypatch, public_url="https://a.b/carrete")
