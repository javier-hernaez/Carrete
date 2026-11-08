"""Administración de la instancia. El administrador gestiona personas y ve la
auditoría y los avisos, pero **no** entra en los espacios ajenos."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DB, AdminAuth, ReqInfo, SettingsDep
from app.db.models import AuditEntry, Membership, Notice, User
from app.services import audit, auth, invitations
from app.services.errors import Conflict, NotFound

router = APIRouter(prefix="/api/v1/admin", tags=["administración"])


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    is_admin: bool
    is_active: bool
    has_totp: bool
    spaces: int
    last_login_at: datetime | None
    created_at: datetime


@router.get("/users", response_model=list[UserOut])
def list_users(current: AdminAuth, db: DB) -> list[UserOut]:
    counts = dict(
        db.execute(select(Membership.user_id, func.count()).group_by(Membership.user_id)).tuples().all()
    )
    users = db.scalars(select(User).order_by(User.display_name))
    return [
        UserOut(
            id=u.id,
            username=u.username,
            display_name=u.display_name,
            is_admin=u.is_admin,
            is_active=u.is_active,
            has_totp=u.has_totp,
            spaces=int(counts.get(u.id, 0)),
            last_login_at=u.last_login_at,
            created_at=u.created_at,
        )
        for u in users
    ]


def _target(db: DB, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("Esa persona no existe")
    return user


class ActiveIn(BaseModel):
    active: bool


@router.post("/users/{user_id}/active", status_code=204)
def set_active(user_id: uuid.UUID, body: ActiveIn, current: AdminAuth, db: DB, info: ReqInfo) -> None:
    auth.require_recent_auth(current.session)
    user = _target(db, user_id)
    if user.id == current.user.id and not body.active:
        raise Conflict("No puedes desactivar tu propia cuenta", code="self")
    user.is_active = body.active
    if not body.active:
        auth.revoke_all(db, user.id)
    audit.record(
        db,
        "user.enabled" if body.active else "user.disabled",
        actor_id=current.user.id,
        target_type="user",
        target_id=user.id,
        request=info,
    )
    db.commit()


@router.post("/users/{user_id}/revoke-sessions", status_code=204)
def revoke_sessions(user_id: uuid.UUID, current: AdminAuth, db: DB, info: ReqInfo) -> None:
    user = _target(db, user_id)
    count = auth.revoke_all(db, user.id, except_id=current.session.id)
    audit.record(
        db,
        "user.sessions_revoked",
        actor_id=current.user.id,
        target_type="user",
        target_id=user.id,
        request=info,
        detail={"count": count},
    )
    db.commit()


class ResetIn(BaseModel):
    reset_totp: bool = False


class LinkOut(BaseModel):
    url: str
    expires_at: datetime


@router.post("/users/{user_id}/reset", response_model=LinkOut)
def reset_access(
    user_id: uuid.UUID, body: ResetIn, current: AdminAuth, db: DB, settings: SettingsDep, info: ReqInfo
) -> LinkOut:
    auth.require_recent_auth(current.session)
    link = invitations.create_reset(
        db, current.user, _target(db, user_id), reset_totp=body.reset_totp, request=info
    )
    db.commit()
    return LinkOut(url=link.url(settings), expires_at=link.invitation.expires_at)


@router.post("/invitations", response_model=LinkOut, status_code=201)
def invite_without_space(current: AdminAuth, db: DB, settings: SettingsDep, info: ReqInfo) -> LinkOut:
    link = invitations.create_invitation(db, current.user, None, None, info)
    db.commit()
    return LinkOut(url=link.url(settings), expires_at=link.invitation.expires_at)


# --- Auditoría -----------------------------------------------------------------------------------------


class AuditOut(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    actor_id: uuid.UUID | None
    actor_name: str | None
    space_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: str | None
    ip: str | None
    detail: dict[str, Any]


class AuditPage(BaseModel):
    items: list[AuditOut]
    next_cursor: str | None


@router.get("/audit", response_model=AuditPage)
def list_audit(
    current: AdminAuth,
    db: DB,
    action: str | None = Query(default=None, max_length=100),
    actor_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
) -> AuditPage:
    query = select(AuditEntry, User.display_name).outerjoin(User, User.id == AuditEntry.actor_id)
    if action:
        query = query.where(AuditEntry.action.startswith(action))
    if actor_id:
        query = query.where(AuditEntry.actor_id == actor_id)
    if since:
        query = query.where(AuditEntry.occurred_at >= since)
    if until:
        query = query.where(AuditEntry.occurred_at < until)
    if cursor:
        query = query.where(AuditEntry.id < uuid.UUID(cursor))
    rows = db.execute(query.order_by(AuditEntry.id.desc()).limit(limit + 1)).tuples().all()
    items = [
        AuditOut(
            id=e.id,
            occurred_at=e.occurred_at,
            actor_id=e.actor_id,
            actor_name=name,
            space_id=e.space_id,
            action=e.action,
            target_type=e.target_type,
            target_id=e.target_id,
            ip=str(e.ip) if e.ip else None,
            detail=e.detail,
        )
        for e, name in rows[:limit]
    ]
    return AuditPage(items=items, next_cursor=str(rows[limit - 1][0].id) if len(rows) > limit else None)


# --- Avisos --------------------------------------------------------------------------------------------


class NoticeOut(BaseModel):
    id: uuid.UUID
    kind: str
    severity: str
    message: str
    detail: dict[str, Any]
    created_at: datetime
    acknowledged_at: datetime | None


@router.get("/notices", response_model=list[NoticeOut])
def list_notices(current: AdminAuth, db: DB, include_acknowledged: bool = False) -> list[NoticeOut]:
    query = select(Notice).order_by(Notice.created_at.desc()).limit(200)
    if not include_acknowledged:
        query = query.where(Notice.acknowledged_at.is_(None))
    return [NoticeOut.model_validate(n, from_attributes=True) for n in db.scalars(query)]


@router.post("/notices/{notice_id}/ack", status_code=204)
def acknowledge(notice_id: uuid.UUID, current: AdminAuth, db: DB) -> None:
    notice = db.get(Notice, notice_id)
    if notice is None:
        raise NotFound("Ese aviso no existe")
    notice.acknowledged_at = datetime.now(UTC)
    notice.acknowledged_by = current.user.id
    db.commit()
