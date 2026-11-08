"""Proceso ``worker``: consume la cola de tareas.

Corre en su propio contenedor, sin acceso a red. Señales:
- ``SIGTERM``/``SIGINT``: termina la tarea en curso y sale (cierre ordenado).
- Escribe un latido en ``/tmp/carrete-worker-alive`` en cada vuelta; el healthcheck lo comprueba.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import socket
import threading
import time
import traceback
from datetime import timedelta
from pathlib import Path
from types import FrameType

from sqlalchemy.orm import Session, sessionmaker

from app.jobs import queue
from app.jobs import tasks as _tasks  # noqa: F401  # registra los manejadores
from app.security import ratelimit

log = logging.getLogger(__name__)

HEARTBEAT = Path("/tmp/carrete-worker-alive")  # noqa: S108  # nosec B108  # tmpfs del contenedor
STALE_AFTER = timedelta(minutes=30)


class Worker:
    def __init__(self, sessions: sessionmaker[Session], *, poll_seconds: float = 2.0) -> None:
        self.sessions = sessions
        self.poll_seconds = poll_seconds
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self.stopping = threading.Event()
        self._last_maintenance = 0.0

    def install_signal_handlers(self) -> None:
        def stop(signum: int, _frame: FrameType | None) -> None:
            log.info("Señal recibida: se termina la tarea en curso y se sale", extra={"signal": signum})
            self.stopping.set()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)

    def run_forever(self) -> None:
        log.info(
            "Worker en marcha", extra={"worker_id": self.worker_id, "kinds": sorted(queue.registered_kinds())}
        )
        while not self.stopping.is_set():
            self.heartbeat()
            self.maintenance()
            if not self.run_once():
                self.stopping.wait(self.poll_seconds)
        log.info("Worker detenido")

    def run_once(self) -> bool:
        """Ejecuta una tarea si hay alguna lista. Devuelve si ha hecho algo."""
        with self.sessions() as session:
            job = queue.claim(session, self.worker_id, queue.registered_kinds())
        if job is None:
            return False

        fn = queue.get_handler(job.kind)
        started = time.perf_counter()
        extra = {"job_id": str(job.id), "kind": job.kind, "attempt": job.attempts}
        try:
            if fn is None:  # pragma: no cover  # claim filtra por tipos registrados
                raise LookupError(f"Sin manejador para «{job.kind}»")
            with self.sessions() as session, session.begin():
                fn(session, job.payload)
        except Exception as exc:
            error = "".join(traceback.format_exception_only(exc)).strip()
            with self.sessions() as session:
                state = queue.mark_failed(session, job, error)
            log.warning("Tarea fallida", extra={**extra, "next_state": state, "error": error})
        else:
            with self.sessions() as session:
                queue.mark_done(session, job.id)
            log.info("Tarea hecha", extra={**extra, "ms": round((time.perf_counter() - started) * 1000)})
        return True

    def maintenance(self) -> None:
        now = time.monotonic()
        if now - self._last_maintenance < 60:
            return
        self._last_maintenance = now
        with self.sessions() as session:
            requeued = queue.requeue_stale(session, STALE_AFTER)
            ratelimit.purge_old(session)
            session.commit()
        if requeued:
            log.warning("Tareas abandonadas devueltas a la cola", extra={"count": requeued})

    @staticmethod
    def heartbeat() -> None:
        with contextlib.suppress(OSError):  # p. ej. en desarrollo sin /tmp escribible
            HEARTBEAT.touch()
