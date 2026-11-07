from __future__ import annotations

import time
import uuid

from app.ids import uuid7, uuid7_time_ms


def test_version_and_variant() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_timestamp_is_current() -> None:
    before = time.time_ns() // 1_000_000
    value = uuid7()
    after = time.time_ns() // 1_000_000
    assert before <= uuid7_time_ms(value) <= after + 1


def test_monotonic_and_unique() -> None:
    values = [uuid7() for _ in range(20_000)]
    assert values == sorted(values)
    assert len(set(values)) == len(values)
