from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Job
from app.jobs import queue
from app.jobs.worker import Worker


def test_backoff_grows_and_caps() -> None:
    assert [queue.backoff_seconds(n) for n in (1, 2, 3, 4, 10)] == [30, 120, 480, 1920, 3600]


def test_enqueue_claim_done(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        job_id = queue.enqueue(s, "noop", {"echo": 1})
        s.commit()
    with sessions() as s:
        job = queue.claim(s, "pruebas")
    assert job is not None and job.id == job_id and job.attempts == 1
    with sessions() as s:
        assert queue.claim(s, "pruebas") is None  # ya está en curso
        queue.mark_done(s, job_id)
        assert queue.counts_by_state(s) == {"done": 1}


def test_priority_and_delay(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        queue.enqueue(s, "noop", {"n": "baja"}, priority=200)
        queue.enqueue(s, "noop", {"n": "alta"}, priority=10)
        queue.enqueue(s, "noop", {"n": "luego"}, priority=1, delay=timedelta(hours=1))
        s.commit()
    with sessions() as s:
        first = queue.claim(s, "w")
        second = queue.claim(s, "w")
        third = queue.claim(s, "w")
    assert first is not None and first.payload == {"n": "alta"}
    assert second is not None and second.payload == {"n": "baja"}
    assert third is None


def test_failures_retry_then_fail(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        job_id = queue.enqueue(s, "noop", max_attempts=2)
        s.commit()
    with sessions() as s:
        job = queue.claim(s, "w")
        assert job is not None
        assert queue.mark_failed(s, job, "uno") == "queued"
        run_after = s.scalar(select(Job.run_after).where(Job.id == job_id))
        assert s.scalar(select(text("now()"))) < run_after  # espera antes de reintentar
        s.execute(update(Job).where(Job.id == job_id).values(run_after=text("now()")))
        s.commit()
        job = queue.claim(s, "w")
        assert job is not None and job.attempts == 2
        assert queue.mark_failed(s, job, "dos") == "failed"
        failed = s.get(Job, job_id)
        assert failed is not None and failed.state == "failed" and failed.last_error == "dos"


def test_skip_locked_never_hands_out_twice(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        for n in range(30):
            queue.enqueue(s, "noop", {"n": n})
        s.commit()
    taken: list[int] = []
    lock = threading.Lock()

    def consume() -> None:
        while True:
            with sessions() as s:
                job = queue.claim(s, threading.current_thread().name)
            if job is None:
                return
            with lock:
                taken.append(job.payload["n"])

    threads = [threading.Thread(target=consume) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(taken) == list(range(30))


def test_requeue_stale(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        job_id = queue.enqueue(s, "noop")
        s.commit()
        assert queue.claim(s, "w") is not None
        s.execute(update(Job).where(Job.id == job_id).values(locked_at=text("now() - interval '2 hours'")))
        s.commit()
        assert queue.requeue_stale(s, timedelta(minutes=30)) == 1
        job = s.get(Job, job_id)
        assert job is not None
        s.refresh(job)
        assert job.state == "queued"


def test_worker_runs_noop_and_failures(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        ok = queue.enqueue(s, "noop", {"echo": "hola"})
        bad = queue.enqueue(s, "noop", {"fail": True}, max_attempts=1)
        unknown = queue.enqueue(s, "tipo-desconocido")
        s.commit()
    worker = Worker(sessions, poll_seconds=0.01)
    worker.maintenance()
    assert worker.run_once()
    assert worker.run_once()
    assert not worker.run_once()  # el tipo desconocido no se toma
    with sessions() as s:
        assert s.get(Job, ok).state == "done"  # type: ignore[union-attr]
        failed = s.get(Job, bad)
        assert failed is not None and failed.state == "failed"
        assert "Fallo pedido" in (failed.last_error or "")
        assert s.get(Job, unknown).state == "queued"  # type: ignore[union-attr]


def test_worker_stops_on_signal(sessions: sessionmaker[Session]) -> None:
    worker = Worker(sessions, poll_seconds=0.01)
    thread = threading.Thread(target=worker.run_forever)
    thread.start()
    worker.stopping.set()
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_duplicate_handler_rejected() -> None:
    with pytest.raises(ValueError, match="Ya hay"):
        queue.handler("noop")(lambda _s, _p: None)
