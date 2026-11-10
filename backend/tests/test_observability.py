from __future__ import annotations

import json
import logging

from app.observability import JsonFormatter, configure_logging, request_id_var


def test_json_lines_include_extras_and_request_id() -> None:
    token = request_id_var.set("abc123")
    try:
        record = logging.makeLogRecord(
            {"name": "x", "levelname": "INFO", "levelno": 20, "msg": "hola %s", "args": ("mundo",)}
        )
        record.kind = "noop"
        record.color_message = "\x1b[36mhola\x1b[0m"
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert line["msg"] == "hola mundo"
    assert line["request_id"] == "abc123"
    assert line["kind"] == "noop"
    assert line["level"] == "info"
    assert "color_message" not in line


def test_configure_logging_disables_uvicorn_access() -> None:
    configure_logging("INFO", "text")
    assert logging.getLogger("uvicorn.access").disabled
    configure_logging("INFO", "json")
