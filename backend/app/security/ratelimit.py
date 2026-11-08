"""Límite de intentos de acceso.

Se cuentan los fallos de los últimos 15 minutos por cuenta y por IP. A partir del quinto, cada nuevo
intento exige esperar el doble que el anterior (1 s, 2 s, 4 s… hasta 15 min). Nunca hay bloqueo
permanente: un atacante no puede dejar fuera al usuario legítimo más que un rato.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import AuthFailure
from app.services.notices import raise_notice

WINDOW = timedelta(minutes=15)
FREE_ATTEMPTS = 5
MAX_WAIT = timedelta(minutes=15)
BURST_NOTICE = 20  # fallos de una misma IP en la ventana que generan aviso


class TooManyAttempts(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Demasiados intentos; espera {retry_after} s")
        self.retry_after = retry_after


def _keys(username: str | None, ip: str | None) -> list[str]:
    keys = []
    if username:
        keys.append(f"user:{username.lower()}")
    if ip:
        keys.append(f"ip:{ip}")
    return keys


def check(db: Session, *, username: str | None, ip: str | None, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    wait = 0.0
    for key in _keys(username, ip):
        count, last = db.execute(
            select(func.count(), func.max(AuthFailure.at)).where(
                AuthFailure.key == key, AuthFailure.at > now - WINDOW
            )
        ).one()
        if count >= FREE_ATTEMPTS and last is not None:
            required = min(timedelta(seconds=2 ** (count - FREE_ATTEMPTS)), MAX_WAIT)
            remaining = (last + required - now).total_seconds()
            wait = max(wait, remaining)
    if wait > 0:
        raise TooManyAttempts(max(1, math.ceil(wait)))


def record_failure(db: Session, *, username: str | None, ip: str | None) -> None:
    for key in _keys(username, ip):
        db.add(AuthFailure(key=key))
    db.flush()
    if ip:
        count = db.scalar(
            select(func.count()).where(
                AuthFailure.key == f"ip:{ip}", AuthFailure.at > datetime.now(UTC) - WINDOW
            )
        )
        if count and count >= BURST_NOTICE:
            raise_notice(
                db,
                "auth_burst",
                f"Muchos intentos fallidos de acceso desde {ip} en los últimos 15 minutos",
                severity="warning",
                dedup_key=f"auth_burst:{ip}",
                detail={"ip": ip, "count": int(count)},
            )


def clear(db: Session, *, username: str) -> None:
    db.execute(delete(AuthFailure).where(AuthFailure.key == f"user:{username.lower()}"))


def purge_old(db: Session) -> int:
    result = db.execute(delete(AuthFailure).where(AuthFailure.at < datetime.now(UTC) - timedelta(days=1)))
    return int(result.rowcount)  # type: ignore[attr-defined]
