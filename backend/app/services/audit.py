"""Registro de auditoría: quién hizo qué, cuándo y desde dónde. Solo inserción."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditEntry


@dataclass(frozen=True)
class RequestInfo:
    ip: str | None = None
    user_agent: str | None = None


def record(
    db: Session,
    action: str,
    *,
    actor_id: uuid.UUID | None = None,
    space_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: object | None = None,
    request: RequestInfo | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEntry(
            action=action,
            actor_id=actor_id,
            space_id=space_id,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            ip=request.ip if request else None,
            user_agent=(request.user_agent or "")[:500] or None if request else None,
            detail=detail or {},
        )
    )
