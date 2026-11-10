from __future__ import annotations

import json

import pytest

from app import cli
from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_check_config_reports_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("DATABASE_URL", "SECRET_KEY", "PUBLIC_URL"):
        monkeypatch.delenv(f"CARRETE_{name}", raising=False)
    with pytest.raises(SystemExit) as info:
        cli.main(["check-config"])
    assert info.value.code == cli.EXIT_CONFIG
    err = capsys.readouterr().err
    assert "CARRETE_SECRET_KEY" in err and "no arranca" in err


def test_check_config_ok(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("CARRETE_DATABASE_URL", "postgresql+psycopg://u:p@db/c")
    monkeypatch.setenv("CARRETE_SECRET_KEY", "x-" + "abcdefghijklmnopqrstuvwxyz0123456789")
    monkeypatch.setenv("CARRETE_PUBLIC_URL", "https://a.b:10000")
    cli.main(["check-config"])
    assert "válida" in capsys.readouterr().out


def test_openapi(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["openapi"])
    spec = json.loads(capsys.readouterr().out)
    assert spec["info"]["title"] == "Carrete"
    assert "/api/v1/info" in spec["paths"]
    assert "/readyz" in spec["paths"]


def test_migrate_command(monkeypatch: pytest.MonkeyPatch, empty_engine, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app import db

    monkeypatch.setenv("CARRETE_DATABASE_URL", str(empty_engine.url.render_as_string(hide_password=False)))
    monkeypatch.setenv("CARRETE_SECRET_KEY", "x-" + "abcdefghijklmnopqrstuvwxyz0123456789")
    monkeypatch.setenv("CARRETE_PUBLIC_URL", "https://a.b:10000")
    monkeypatch.setenv("CARRETE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CARRETE_LOG_FORMAT", "text")
    db.get_engine.cache_clear()
    try:
        cli.main(["migrate"])
    finally:
        db.get_engine.cache_clear()
    from app.migrate import is_up_to_date

    assert is_up_to_date(empty_engine)
