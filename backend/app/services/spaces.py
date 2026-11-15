"""Espacios, miembros y roles. Toda consulta sobre un espacio pasa por ``access``:
exige pertenencia comprobada y responde 404 a lo ajeno. El administrador de la instancia es la
excepción: tiene acceso de propietario a todos los espacios aunque no sea miembro."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.models import Membership, Space, User
from app.services import audit
from app.services.audit import RequestInfo
from app.services.errors import Conflict, Forbidden, Invalid, NotFound

RANK = {"viewer": 0, "collaborator": 1, "owner": 2}
MAX_NAME = 80


@dataclass(frozen=True)
class SpaceAccess:
    space: Space
    membership: Membership

    @property
    def role(self) -> str:
        return self.membership.role

    def can(self, minimum: str) -> bool:
        return RANK[self.role] >= RANK[minimum]


def _as_admin(space: Space, user: User, membership: Membership | None) -> SpaceAccess:
    """Acceso del administrador: propietario en cualquier espacio. Si no es miembro, la
    pertenencia es virtual: no se guarda, así que no aparece en la lista de miembros."""
    if membership is not None and membership.role == "owner":
        return SpaceAccess(space, membership)
    return SpaceAccess(space, Membership(space_id=space.id, user_id=user.id, role="owner"))


def access(db: Session, user: User, space_id: uuid.UUID, minimum: str = "viewer") -> SpaceAccess:
    if user.is_admin:
        space = db.get(Space, space_id)
        if space is None:
            raise NotFound("Ese espacio no existe")
        own = db.scalar(
            select(Membership).where(Membership.space_id == space_id, Membership.user_id == user.id)
        )
        return _as_admin(space, user, own)
    row = db.execute(
        select(Space, Membership)
        .join(Membership, Membership.space_id == Space.id)
        .where(Space.id == space_id, Membership.user_id == user.id)
    ).first()
    if row is None:
        raise NotFound("Ese espacio no existe")
    result = SpaceAccess(*row.tuple())
    if not result.can(minimum):
        if result.role == "viewer" and minimum != "viewer":
            raise Forbidden("Con el rol de lector no puedes hacer cambios en este espacio")
        raise Forbidden("Solo el propietario del espacio puede hacer esto")
    return result


def _clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise Invalid("El nombre no puede estar vacío", code="invalid_name")
    if len(name) > MAX_NAME:
        raise Invalid(f"El nombre no puede tener más de {MAX_NAME} caracteres", code="invalid_name")
    return name


def list_for_user(db: Session, user: User, *, include_archived: bool = True) -> list[SpaceAccess]:
    if user.is_admin:
        admin_query = (
            select(Space, Membership)
            .outerjoin(Membership, and_(Membership.space_id == Space.id, Membership.user_id == user.id))
            .order_by(Space.archived_at.is_not(None), Space.name)
        )
        if not include_archived:
            admin_query = admin_query.where(Space.archived_at.is_(None))
        return [_as_admin(space, user, membership) for space, membership in db.execute(admin_query).tuples()]
    query = (
        select(Space, Membership)
        .join(Membership, Membership.space_id == Space.id)
        .where(Membership.user_id == user.id)
        .order_by(Space.archived_at.is_not(None), Space.name)
    )
    if not include_archived:
        query = query.where(Space.archived_at.is_(None))
    return [SpaceAccess(*row.tuple()) for row in db.execute(query)]


def create(db: Session, user: User, name: str, request: RequestInfo) -> SpaceAccess:
    space = Space(name=_clean_name(name), created_by=user.id)
    db.add(space)
    db.flush()
    membership = Membership(space_id=space.id, user_id=user.id, role="owner")
    db.add(membership)
    db.flush()
    audit.record(
        db, "space.created", actor_id=user.id, space_id=space.id, request=request, detail={"name": space.name}
    )
    return SpaceAccess(space, membership)


def rename(db: Session, acc: SpaceAccess, user: User, name: str, request: RequestInfo) -> None:
    old = acc.space.name
    acc.space.name = _clean_name(name)
    audit.record(
        db,
        "space.renamed",
        actor_id=user.id,
        space_id=acc.space.id,
        request=request,
        detail={"from": old, "to": acc.space.name},
    )


def set_archived(db: Session, acc: SpaceAccess, user: User, archived: bool, request: RequestInfo) -> None:
    acc.space.archived_at = datetime.now(UTC) if archived else None
    audit.record(
        db,
        "space.archived" if archived else "space.unarchived",
        actor_id=user.id,
        space_id=acc.space.id,
        request=request,
    )


def members(db: Session, space_id: uuid.UUID) -> list[tuple[Membership, User]]:
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.space_id == space_id)
        .order_by(User.display_name)
    )
    return [row.tuple() for row in rows]


def _owner_count(db: Session, space_id: uuid.UUID) -> int:
    return int(
        db.scalar(select(func.count()).where(Membership.space_id == space_id, Membership.role == "owner"))
        or 0
    )


def change_role(
    db: Session, acc: SpaceAccess, actor: User, member_id: uuid.UUID, role: str, request: RequestInfo
) -> Membership:
    if role not in RANK:
        raise Invalid("Rol desconocido", code="invalid_role")
    membership = db.scalar(
        select(Membership).where(Membership.space_id == acc.space.id, Membership.user_id == member_id)
    )
    if membership is None:
        raise NotFound("Esa persona no es miembro del espacio")
    if membership.role == "owner" and role != "owner" and _owner_count(db, acc.space.id) <= 1:
        raise Conflict("El espacio necesita al menos un propietario", code="last_owner")
    old = membership.role
    membership.role = role
    audit.record(
        db,
        "space.role_changed",
        actor_id=actor.id,
        space_id=acc.space.id,
        target_type="user",
        target_id=member_id,
        request=request,
        detail={"from": old, "to": role},
    )
    return membership


def remove_member(
    db: Session, acc: SpaceAccess, actor: User, member_id: uuid.UUID, request: RequestInfo
) -> None:
    membership = db.scalar(
        select(Membership).where(Membership.space_id == acc.space.id, Membership.user_id == member_id)
    )
    if membership is None:
        raise NotFound("Esa persona no es miembro del espacio")
    if membership.role == "owner" and _owner_count(db, acc.space.id) <= 1:
        raise Conflict("El espacio necesita al menos un propietario", code="last_owner")
    db.delete(membership)
    audit.record(
        db,
        "space.member_removed",
        actor_id=actor.id,
        space_id=acc.space.id,
        target_type="user",
        target_id=member_id,
        request=request,
    )


def add_member(db: Session, space_id: uuid.UUID, user_id: uuid.UUID, role: str) -> Membership:
    existing = db.scalar(
        select(Membership).where(Membership.space_id == space_id, Membership.user_id == user_id)
    )
    if existing is not None:
        if RANK[role] > RANK[existing.role]:
            existing.role = role
        return existing
    membership = Membership(space_id=space_id, user_id=user_id, role=role)
    db.add(membership)
    db.flush()
    return membership


def default_space_id(db: Session, user: User) -> uuid.UUID | None:
    """El último espacio usado si sigue siendo miembro; si no, el primero no archivado."""
    spaces = list_for_user(db, user)
    ids = {acc.space.id for acc in spaces}
    if user.last_space_id in ids:
        return user.last_space_id
    active = [acc for acc in spaces if acc.space.archived_at is None]
    return (active or spaces)[0].space.id if spaces else None
