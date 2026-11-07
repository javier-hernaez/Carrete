"""Cola de tareas sobre PostgreSQL (ADR 0002).

- Cada tarea se toma con ``FOR UPDATE SKIP LOCKED``: varios procesos pueden consumir sin pisarse.
- Reintentos con espera creciente (``backoff_seconds``). Al agotar los intentos queda en ``failed`` y
  se ve en el panel de administración; nunca se borra sola.
- Si un proceso muere a mitad de tarea, ``requeue_stale`` la devuelve a la cola pasado un tiempo.
- Los manejadores deben ser idempotentes: una tarea puede ejecutarse más de una vez.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import Job

Handler = Callable[[Session, dict[str, Any]], None]

_handlers: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    """Registra la función que ejecuta las tareas de tipo ``kind``."""

    def register(fn: Handler) -> Handler:
        if kind in _handlers and _handlers[kind] is not fn:
            raise ValueError(f"Ya hay un manejador para «{kind}»")
        _handlers[kind] = fn
        return fn

    return register


def get_handler(kind: str) -> Handler | None:
    return _handlers.get(kind)


def registered_kinds() -> frozenset[str]:
    return frozenset(_handlers)


def backoff_seconds(attempt: int) -> int:
    """Espera antes del intento ``attempt + 1``: 30 s, 2 min, 8 min, … hasta 1 hora."""
    return int(min(30 * 4 ** max(attempt - 1, 0), 3600))


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


def enqueue(
    session: Session,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    priority: int = 100,
    max_attempts: int = 3,
    delay: timedelta | None = None,
) -> uuid.UUID:
    job = Job(kind=kind, payload=payload or {}, priority=priority, max_attempts=max_attempts)
    if delay is not None:
        job.run_after = func.now() + delay  # type: ignore[assignment]
    session.add(job)
    session.flush()
    return job.id


def claim(session: Session, worker_id: str, kinds: frozenset[str] | None = None) -> ClaimedJob | None:
    """Toma la siguiente tarea lista y la marca como en curso. Confirma la transacción."""
    query = (
        select(Job)
        .where(Job.state == "queued", Job.run_after <= func.now())
        .order_by(Job.priority, Job.run_after, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if kinds is not None:
        query = query.where(Job.kind.in_(kinds))
    job = session.scalars(query).first()
    if job is None:
        session.rollback()
        return None
    job.state = "running"
    job.attempts += 1
    job.locked_at = func.now()  # type: ignore[assignment]
    job.locked_by = worker_id
    claimed = ClaimedJob(job.id, job.kind, dict(job.payload), job.attempts, job.max_attempts)
    session.commit()
    return claimed


def mark_done(session: Session, job_id: uuid.UUID) -> None:
    session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(state="done", finished_at=func.now(), locked_at=None, locked_by=None, last_error=None)
    )
    session.commit()


def mark_failed(session: Session, job: ClaimedJob, error: str) -> str:
    """Anota el fallo. Devuelve el nuevo estado: ``queued`` (se reintentará) o ``failed``."""
    final = job.attempts >= job.max_attempts
    values: dict[str, Any] = {"last_error": error[:4000], "locked_at": None, "locked_by": None}
    if final:
        values |= {"state": "failed", "finished_at": func.now()}
    else:
        values |= {
            "state": "queued",
            "run_after": func.now() + timedelta(seconds=backoff_seconds(job.attempts)),
        }
    session.execute(update(Job).where(Job.id == job.id).values(**values))
    session.commit()
    return "failed" if final else "queued"


def requeue_stale(session: Session, older_than: timedelta) -> int:
    """Devuelve a la cola las tareas «en curso» abandonadas (el proceso que las tomó murió)."""
    result = session.execute(
        update(Job)
        .where(Job.state == "running", Job.locked_at < func.now() - older_than)
        .values(state="queued", locked_at=None, locked_by=None, last_error="Abandonada: se reintenta")
    )
    session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


def counts_by_state(session: Session) -> dict[str, int]:
    rows = session.execute(select(Job.state, func.count()).group_by(Job.state)).all()
    return {state: int(count) for state, count in rows}
