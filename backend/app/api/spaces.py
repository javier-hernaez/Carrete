"""Rutas de espacios, miembros e invitaciones."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.api.auth import StageOut, set_session_cookie
from app.api.deps import DB, FullAuth, OptionalAuth, ReqInfo, SettingsDep
from app.services import invitations, spaces

router = APIRouter(prefix="/api/v1", tags=["espacios"])

Role = Literal["owner", "collaborator", "viewer"]


class SpaceOut(BaseModel):
    id: uuid.UUID
    name: str
    role: Role
    archived: bool
    created_at: datetime


def space_out(acc: spaces.SpaceAccess) -> SpaceOut:
    return SpaceOut(
        id=acc.space.id,
        name=acc.space.name,
        role=acc.role,  # type: ignore[arg-type]
        archived=acc.space.archived_at is not None,
        created_at=acc.space.created_at,
    )


class SpaceIn(BaseModel):
    name: str = Field(max_length=200)


class SpacePatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    archived: bool | None = None


@router.get("/spaces", response_model=list[SpaceOut])
def list_spaces(current: FullAuth, db: DB) -> list[SpaceOut]:
    return [space_out(acc) for acc in spaces.list_for_user(db, current.user)]


@router.post("/spaces", response_model=SpaceOut, status_code=201)
def create_space(body: SpaceIn, current: FullAuth, db: DB, info: ReqInfo) -> SpaceOut:
    acc = spaces.create(db, current.user, body.name, info)
    current.user.last_space_id = acc.space.id
    db.commit()
    return space_out(acc)


@router.get("/spaces/{space_id}", response_model=SpaceOut)
def get_space(space_id: uuid.UUID, current: FullAuth, db: DB) -> SpaceOut:
    return space_out(spaces.access(db, current.user, space_id))


@router.patch("/spaces/{space_id}", response_model=SpaceOut)
def update_space(space_id: uuid.UUID, body: SpacePatch, current: FullAuth, db: DB, info: ReqInfo) -> SpaceOut:
    acc = spaces.access(db, current.user, space_id, "owner")
    if body.name is not None:
        spaces.rename(db, acc, current.user, body.name, info)
    if body.archived is not None:
        spaces.set_archived(db, acc, current.user, body.archived, info)
    db.commit()
    return space_out(acc)


# --- Miembros ------------------------------------------------------------------------------------------


class MemberOut(BaseModel):
    user_id: uuid.UUID
    username: str
    display_name: str
    role: Role
    is_you: bool


class RoleIn(BaseModel):
    role: Role


@router.get("/spaces/{space_id}/members", response_model=list[MemberOut])
def list_members(space_id: uuid.UUID, current: FullAuth, db: DB) -> list[MemberOut]:
    spaces.access(db, current.user, space_id)
    return [
        MemberOut(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=m.role,  # type: ignore[arg-type]
            is_you=user.id == current.user.id,
        )
        for m, user in spaces.members(db, space_id)
    ]


@router.patch("/spaces/{space_id}/members/{user_id}", status_code=204)
def change_member_role(
    space_id: uuid.UUID, user_id: uuid.UUID, body: RoleIn, current: FullAuth, db: DB, info: ReqInfo
) -> None:
    acc = spaces.access(db, current.user, space_id, "owner")
    spaces.change_role(db, acc, current.user, user_id, body.role, info)
    db.commit()


@router.delete("/spaces/{space_id}/members/{user_id}", status_code=204)
def remove_member(space_id: uuid.UUID, user_id: uuid.UUID, current: FullAuth, db: DB, info: ReqInfo) -> None:
    # Cualquiera puede salir de un espacio; para echar a otro hay que ser propietario.
    minimum = "viewer" if user_id == current.user.id else "owner"
    acc = spaces.access(db, current.user, space_id, minimum)
    spaces.remove_member(db, acc, current.user, user_id, info)
    db.commit()


# --- Invitaciones --------------------------------------------------------------------------------------


class InvitationIn(BaseModel):
    role: Role = "collaborator"


class InvitationOut(BaseModel):
    id: uuid.UUID
    role: Role | None
    url: str | None = None
    created_at: datetime
    expires_at: datetime


@router.get("/spaces/{space_id}/invitations", response_model=list[InvitationOut])
def list_invitations(space_id: uuid.UUID, current: FullAuth, db: DB) -> list[InvitationOut]:
    spaces.access(db, current.user, space_id, "owner")
    return [
        InvitationOut(id=i.id, role=i.role, created_at=i.created_at, expires_at=i.expires_at)  # type: ignore[arg-type]
        for i in invitations.pending_invitations(db, space_id)
    ]


@router.post("/spaces/{space_id}/invitations", response_model=InvitationOut, status_code=201)
def create_invitation(
    space_id: uuid.UUID, body: InvitationIn, current: FullAuth, db: DB, settings: SettingsDep, info: ReqInfo
) -> InvitationOut:
    link = invitations.create_invitation(db, current.user, space_id, body.role, info)
    db.commit()
    inv = link.invitation
    return InvitationOut(
        id=inv.id, role=inv.role, url=link.url(settings), created_at=inv.created_at, expires_at=inv.expires_at
    )  # type: ignore[arg-type]


@router.delete("/invitations/{invitation_id}", status_code=204)
def revoke_invitation(invitation_id: uuid.UUID, current: FullAuth, db: DB, info: ReqInfo) -> None:
    invitations.revoke_invitation(db, current.user, invitation_id, info)
    db.commit()


class InvitationPreview(BaseModel):
    space_name: str | None
    role: Role | None
    invited_by: str | None
    expires_at: datetime


@router.get("/invitations/by-token/{token}", response_model=InvitationPreview)
def preview_invitation(token: str, db: DB) -> InvitationPreview:
    return InvitationPreview(**invitations.preview(db, token))  # type: ignore[arg-type]


class AcceptIn(BaseModel):
    username: str | None = Field(default=None, max_length=64)
    display_name: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, max_length=512)


class AcceptOut(BaseModel):
    stage: Literal["full", "totp", "enroll"]
    space_id: uuid.UUID | None


@router.post("/invitations/by-token/{token}/accept", response_model=AcceptOut)
def accept_invitation(
    token: str,
    body: AcceptIn,
    response: Response,
    current: OptionalAuth,
    db: DB,
    settings: SettingsDep,
    info: ReqInfo,
) -> AcceptOut:
    if current is not None and current.session.stage == "full":
        space_id = invitations.accept_as_existing_user(db, token, current.user, info)
        db.commit()
        return AcceptOut(stage="full", space_id=space_id)
    issued, space_id = invitations.accept_as_new_user(
        db,
        settings,
        token,
        username=body.username or "",
        display_name=body.display_name or "",
        password=body.password or "",
        request=info,
    )
    db.commit()
    set_session_cookie(response, settings, issued.token)
    return AcceptOut(stage=issued.session.stage, space_id=space_id)  # type: ignore[arg-type]


# --- Restablecer acceso --------------------------------------------------------------------------------


class ResetPreview(BaseModel):
    username: str | None
    reset_totp: bool


class ResetIn(BaseModel):
    password: str = Field(max_length=512)


@router.get("/password-resets/{token}", response_model=ResetPreview)
def preview_reset(token: str, db: DB) -> ResetPreview:
    return ResetPreview(**invitations.reset_preview(db, token))  # type: ignore[arg-type]


@router.post("/password-resets/{token}", response_model=StageOut)
def use_reset(token: str, body: ResetIn, db: DB, info: ReqInfo) -> StageOut:
    invitations.use_reset(db, token, body.password, info)
    db.commit()
    return StageOut(stage="full")
