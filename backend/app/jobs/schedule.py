"""Tareas periódicas: el worker las encola cuando toca (purga nocturna, uso de disco, avisos…)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import AppState
from app.jobs import queue

PERIODIC: dict[str, timedelta] = {
    "purge_trash": timedelta(hours=24),
    "storage_report": timedelta(hours=1),
    "health_checks": timedelta(minutes=15),
    "expire_exports": timedelta(hours=6),
    "build_library": timedelta(hours=24),
    "backfill_places": timedelta(hours=1),
}


def due(db: Session, name: str, every: timedelta, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    key = f"schedule:{name}"
    state = db.get(AppState, key, with_for_update=True)
    last = state.value.get("last") if state else None
    if last and datetime.fromisoformat(last) > now - every:
        return False
    db.execute(
        insert(AppState)
        .values(key=key, value={"last": now.isoformat()})
        .on_conflict_do_update(
            index_elements=["key"], set_={"value": {"last": now.isoformat()}, "updated_at": now}
        )
    )
    return True


def enqueue_due(db: Session) -> list[str]:
    started = []
    for name, every in PERIODIC.items():
        if due(db, name, every):
            queue.enqueue(db, name, priority=200)
            started.append(name)
    db.commit()
    return started
