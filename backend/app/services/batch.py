"""Acciones sobre varios elementos a la vez. Todo pasa por el control de acceso del espacio y
solo afecta a elementos de ese espacio: los identificadores ajenos se ignoran."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import User
from app.services import spaces, trash
from app.services.audit import RequestInfo
from app.services.errors import Invalid

# Rol mínimo de cada acción.
MINIMUM_ROLE = {"trash": "collaborator", "restore": "collaborator"}


def apply(
    db: Session,
    user: User,
    space_id: uuid.UUID,
    ids: list[uuid.UUID],
    action: str,
    params: dict[str, Any],
    request: RequestInfo,
) -> int:
    minimum = MINIMUM_ROLE.get(action)
    if minimum is None:
        raise Invalid("Acción desconocida", code="invalid_action")
    acc = spaces.access(db, user, space_id, minimum)
    if action == "trash":
        return trash.move_to_trash(db, acc, user, ids, request)
    return trash.restore(db, acc, user, ids, request)
