"""Avisos internos al administrador. Sin servicios externos: se ven en la aplicación."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Notice
from app.ids import uuid7


def raise_notice(
    db: Session,
    kind: str,
    message: str,
    *,
    severity: str = "warning",
    dedup_key: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Crea un aviso. Si ya hay uno abierto con la misma ``dedup_key``, no se repite."""
    stmt = insert(Notice).values(
        id=uuid7(), kind=kind, severity=severity, message=message, dedup_key=dedup_key, detail=detail or {}
    )
    if dedup_key is not None:
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["dedup_key"],
            index_where=Notice.acknowledged_at.is_(None) & Notice.dedup_key.is_not(None),
        )
    db.execute(stmt)


def open_notices(db: Session) -> list[Notice]:
    return list(
        db.scalars(select(Notice).where(Notice.acknowledged_at.is_(None)).order_by(Notice.created_at.desc()))
    )
