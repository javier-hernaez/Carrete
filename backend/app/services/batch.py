"""Acciones sobre varios elementos a la vez con deshacer.

Todo pasa por el control de acceso del espacio y solo afecta a elementos de ese espacio (los
identificadores ajenos se ignoran sin revelar nada). Cada acción devuelve la operación inversa exacta:
antes de aplicarla se guarda una instantánea de los campos que cambia, elemento a elemento.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Asset, User
from app.services import albums, audit, spaces, tags, trash
from app.services.audit import RequestInfo
from app.services.errors import Invalid

MINIMUM_ROLE = {
    "trash": "collaborator",
    "restore": "collaborator",
    "review": "collaborator",
    "favorite": "collaborator",
    "add_album": "collaborator",
    "remove_album": "collaborator",
    "add_tag": "collaborator",
    "remove_tag": "collaborator",
    "set_date": "collaborator",
    "shift_date": "collaborator",
    "revert": "collaborator",
    "set_location": "collaborator",
}

REVERTIBLE = {
    "review_state",
    "is_favorite",
    "taken_at_local",
    "taken_at_offset",
    "taken_at_source",
    "in_album",
    "has_tag",
    "lat",
    "lon",
    "place_id",
    "place_name",
    "place_region",
    "place_country",
}
LOCATION_FIELDS = ["lat", "lon", "place_id", "place_name", "place_region", "place_country"]
REVIEW_STATES = {"pending", "kept", "discarded"}


def _snapshot(db: Session, ids: list[uuid.UUID], fields: list[str]) -> dict[str, dict[str, Any]]:
    columns = [getattr(Asset, f) for f in fields]
    rows = db.execute(select(Asset.id, *columns).where(Asset.id.in_(ids))).all()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        values = {}
        for field, value in zip(fields, row[1:], strict=True):
            values[field] = value.isoformat() if isinstance(value, datetime) else value
        out[str(row[0])] = values
    return out


def apply(
    db: Session,
    user: User,
    space_id: uuid.UUID,
    ids: list[uuid.UUID],
    action: str,
    params: dict[str, Any],
    request: RequestInfo,
) -> tuple[int, dict[str, Any] | None]:
    """Aplica la acción. Devuelve (cuántos cambiaron, operación para deshacer)."""
    minimum = MINIMUM_ROLE.get(action)
    if minimum is None:
        raise Invalid("Acción desconocida", code="invalid_action")
    acc = spaces.access(db, user, space_id, minimum)
    valid = list(db.scalars(select(Asset.id).where(Asset.space_id == space_id, Asset.id.in_(ids))))
    if not valid:
        return 0, None
    in_space = Asset.id.in_(valid)

    if action == "trash":
        return trash.move_to_trash(db, acc, user, valid, request), {"action": "restore"}
    if action == "restore":
        return trash.restore(db, acc, user, valid, request), {"action": "trash"}

    if action == "review":
        state = params.get("state")
        if state not in REVIEW_STATES:
            raise Invalid("Estado de revisión desconocido", code="invalid_state")
        before = _snapshot(db, valid, ["review_state"])
        count = _rowcount(
            db.execute(update(Asset).where(in_space, Asset.review_state != state).values(review_state=state))
        )
        return count, {"action": "revert", "snapshot": before}

    if action == "favorite":
        value = bool(params.get("value", True))
        before = _snapshot(db, valid, ["is_favorite"])
        count = _rowcount(
            db.execute(
                update(Asset).where(in_space, Asset.is_favorite.is_not(value)).values(is_favorite=value)
            )
        )
        return count, {"action": "revert", "snapshot": before}

    if action in ("add_album", "remove_album"):
        album = albums.get(db, space_id, _uuid(params.get("album_id"), "album_id"))
        present = albums.membership(db, album.id, valid)
        before = {str(i): {"in_album": i in present} for i in valid}
        if action == "add_album":
            ordered = [i for i in ids if i in set(valid)]
            count = albums.add_assets(db, album, ordered, user.id)
            audit.record(
                db,
                "album.assets_added",
                actor_id=user.id,
                space_id=space_id,
                target_type="album",
                target_id=album.id,
                request=request,
                detail={"count": count, "album": album.name},
            )
        else:
            count = albums.remove_assets(db, album, valid)
        return count, {"action": "revert", "snapshot": before, "album_id": str(album.id)}

    if action in ("add_tag", "remove_tag"):
        tag = tags.get(db, space_id, _uuid(params.get("tag_id"), "tag_id"))
        present = tags.membership(db, tag.id, valid)
        before = {str(i): {"has_tag": i in present} for i in valid}
        if action == "add_tag":
            count = tags.add_assets(db, tag, valid, user.id)
        else:
            count = tags.remove_assets(db, tag, valid)
        return count, {"action": "revert", "snapshot": before, "tag_id": str(tag.id)}

    if action in ("set_date", "shift_date"):
        before = _snapshot(db, valid, ["taken_at_local", "taken_at_offset", "taken_at_source"])
        if action == "set_date":
            when = _parse_datetime(params.get("taken_at"))
            offset = params.get("offset_minutes")
            if offset is not None and not (isinstance(offset, int) and -840 <= offset <= 840):
                raise Invalid("Desfase horario no válido", code="invalid_offset")
            values: dict[str, Any] = {"taken_at_local": when, "taken_at_source": "manual"}
            if "offset_minutes" in params:
                values["taken_at_offset"] = offset
            count = _rowcount(db.execute(update(Asset).where(in_space).values(**values)))
        else:
            minutes = params.get("minutes")
            if not isinstance(minutes, int) or minutes == 0 or abs(minutes) > 100 * 365 * 24 * 60:
                raise Invalid("Desplazamiento no válido", code="invalid_shift")
            count = _rowcount(
                db.execute(
                    update(Asset)
                    .where(in_space)
                    .values(
                        taken_at_local=Asset.taken_at_local + timedelta(minutes=minutes),
                        taken_at_source="manual",
                    )
                )
            )
        audit.record(
            db,
            "asset.date_changed",
            actor_id=user.id,
            space_id=space_id,
            request=request,
            detail={"count": count, "action": action},
        )
        return count, {"action": "revert", "snapshot": before}

    if action == "set_location":
        # Asignar o corregir la ubicación a mano; sin lat/lon, se quita.
        before = _snapshot(db, valid, LOCATION_FIELDS)
        lat, lon = params.get("lat"), params.get("lon")
        if (lat is None) != (lon is None):
            raise Invalid("Hacen falta latitud y longitud", code="invalid_location")
        from app.services.geo import assign_place

        count = 0
        for asset in db.scalars(select(Asset).where(in_space)):
            asset.lat, asset.lon = (
                (float(lat), float(lon)) if lat is not None and lon is not None else (None, None)
            )
            assign_place(asset)
            count += 1
        return count, {"action": "revert", "snapshot": before}

    # revert: vuelve a dejar cada elemento como estaba según la instantánea de una acción anterior.
    return _revert(db, space_id, valid, params, user), None


def _revert(
    db: Session, space_id: uuid.UUID, valid: list[uuid.UUID], params: dict[str, Any], user: User
) -> int:
    snapshot = params.get("snapshot")
    if not isinstance(snapshot, dict):
        raise Invalid("Falta la instantánea para deshacer", code="invalid_snapshot")
    allowed = {str(i) for i in valid}
    album = (
        albums.get(db, space_id, _uuid(params["album_id"], "album_id")) if params.get("album_id") else None
    )
    tag = tags.get(db, space_id, _uuid(params["tag_id"], "tag_id")) if params.get("tag_id") else None
    count = 0
    for key, values in snapshot.items():
        if key not in allowed or not isinstance(values, dict) or not set(values) <= REVERTIBLE:
            continue
        asset_id = uuid.UUID(key)
        if "in_album" in values:
            if album is None:
                raise Invalid("Falta el álbum para deshacer", code="invalid_snapshot")
            if values["in_album"]:
                count += albums.add_assets(db, album, [asset_id], user.id)
            else:
                count += albums.remove_assets(db, album, [asset_id])
            continue
        if "has_tag" in values:
            if tag is None:
                raise Invalid("Falta la etiqueta para deshacer", code="invalid_snapshot")
            if values["has_tag"]:
                count += tags.add_assets(db, tag, [asset_id], user.id)
            else:
                count += tags.remove_assets(db, tag, [asset_id])
            continue
        changes = dict(values)
        if "review_state" in changes and changes["review_state"] not in REVIEW_STATES:
            continue
        if "taken_at_local" in changes:
            changes["taken_at_local"] = _parse_datetime(changes["taken_at_local"])
        count += _rowcount(db.execute(update(Asset).where(Asset.id == asset_id).values(**changes)))
    return count


def _rowcount(result: Any) -> int:
    return int(result.rowcount)


def _uuid(value: Any, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise Invalid(f"Falta «{name}»", code="invalid_params") from exc


def _parse_datetime(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise Invalid("Fecha no válida (AAAA-MM-DDTHH:MM:SS)", code="invalid_date") from exc
    return parsed.replace(tzinfo=None)  # hora de pared
