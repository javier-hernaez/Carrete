"""Exportaciones.

- Siempre los originales, sin recomprimir. ZIP sin compresión (las fotos ya lo están) y ZIP64.
- Volúmenes de tamaño configurable (4 GB por defecto). Cada volumen es un ZIP completo e independiente:
  se abre con cualquier programa sin necesidad de los demás. Se descargan con peticiones Range.
- Incluye ``carrete-manifest.json`` y ``carrete-manifest.csv`` (fecha, álbumes, estado, favorita,
  descripción, ubicación, quién la subió y SHA-256 de cada elemento).
- Antes de empezar se comprueba el espacio libre. Caducan a los 7 días.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import shutil
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Album, AlbumAsset, Asset, Blob, Export, User
from app.jobs import queue
from app.services import audit, spaces
from app.services.audit import RequestInfo
from app.services.errors import Forbidden, Invalid, NotFound
from app.storage.files import Storage
from app.storage.naming import UniqueNames, file_name, folders_for, safe_component

log = logging.getLogger(__name__)

INCLUDE = {"kept": ["kept"], "kept_pending": ["kept", "pending"], "all": ["kept", "pending", "discarded"]}
STRUCTURES = {"album", "date", "flat"}
CHUNK = 1024 * 1024
ZIP_OVERHEAD = 200  # cabeceras por fichero, de sobra


class InsufficientSpace(Invalid):
    status = 507
    code = "disk_full"


def _selected_assets(db: Session, space_id: uuid.UUID, params: dict[str, Any]) -> list[tuple[Asset, Blob]]:
    query = (
        select(Asset, Blob)
        .join(Blob, Blob.id == Asset.blob_id)
        .where(Asset.space_id == space_id, Asset.trashed_at.is_(None))
    )
    if params.get("ids"):
        query = query.where(Asset.id.in_([uuid.UUID(i) for i in params["ids"]]))
    else:
        query = query.where(Asset.review_state.in_(INCLUDE[params.get("include", "kept_pending")]))
    if params.get("album_ids"):
        query = query.where(
            Asset.id.in_(
                select(AlbumAsset.asset_id).where(
                    AlbumAsset.album_id.in_([uuid.UUID(a) for a in params["album_ids"]])
                )
            )
        )
    return list(db.execute(query.order_by(Asset.taken_at_local, Asset.id)).tuples())


def create(
    db: Session,
    settings: Settings,
    storage: Storage,
    user: User,
    space_id: uuid.UUID,
    params: dict[str, Any],
    request: RequestInfo,
) -> Export:
    scope = "selection" if params.get("ids") else "albums" if params.get("album_ids") else "space"
    # Exportar todo el espacio es cosa del propietario; un álbum o una selección, de cualquiera.
    acc = spaces.access(db, user, space_id, "owner" if scope == "space" else "viewer")
    if params.get("structure", "album") not in STRUCTURES:
        raise Invalid("Estructura desconocida", code="invalid_structure")
    if params.get("include", "kept_pending") not in INCLUDE:
        raise Invalid("Qué incluir: kept, kept_pending o all", code="invalid_include")
    target = params.get("target", "zip")
    if target == "folder":
        if not user.is_admin:
            raise Forbidden("Solo el administrador puede exportar a una carpeta del servidor")
        params["folder"] = str(allowed_folder(settings, str(params.get("folder", ""))))
    elif target != "zip":
        raise Invalid("Destino desconocido", code="invalid_target")
    for album_id in params.get("album_ids") or []:
        album = db.get(Album, uuid.UUID(album_id))
        if album is None or album.space_id != space_id:
            raise NotFound("Ese álbum no existe")

    items = _selected_assets(db, space_id, params)
    if not items:
        raise Invalid("No hay nada que exportar con esas opciones", code="empty_export")
    total = sum(blob.size_bytes for _, blob in items)
    if target == "zip" and storage.free_bytes() - total * 1.02 < settings.min_free_bytes:
        raise InsufficientSpace(
            f"No hay espacio libre para preparar esta exportación ({total / 1e9:.1f} GB). "
            "Avisa al administrador."
        )
    export = Export(
        space_id=space_id,
        requested_by=user.id,
        params={
            "scope": scope,
            "target": target,
            "structure": params.get("structure", "album"),
            "naming": params.get("naming", "normalized"),
            "include": params.get("include", "kept_pending"),
            "ids": params.get("ids") or [],
            "album_ids": params.get("album_ids") or [],
            "volume_bytes": int(params.get("volume_bytes") or settings.export_volume_bytes),
            **({"folder": params["folder"]} if target == "folder" else {}),
        },
        total_items=len(items),
        total_bytes=total,
        expires_at=datetime.now(UTC) + timedelta(days=settings.export_ttl_days),
    )
    db.add(export)
    db.flush()
    queue.enqueue(db, "build_export", {"export_id": str(export.id)}, priority=120, max_attempts=2)
    audit.record(
        db,
        "export.created",
        actor_id=user.id,
        space_id=acc.space.id,
        target_type="export",
        target_id=export.id,
        request=request,
        detail={"scope": scope, "count": len(items), "bytes": total, "target": target},
    )
    return export


def allowed_folder(settings: Settings, folder: str) -> Path:
    """Solo dentro de las carpetas permitidas en ``CARRETE_EXPORT_ROOTS`` (sin escaparse con «..»)."""
    if not settings.export_roots:
        raise Forbidden("No hay carpetas de exportación configuradas (CARRETE_EXPORT_ROOTS)")
    path = Path(folder).resolve()
    for root in settings.export_roots:
        if path.is_relative_to(root.resolve()) and root.resolve().exists():
            return path
    raise Forbidden("Esa carpeta no está entre las permitidas")


def _manifest_rows(
    db: Session, export: Export, items: list[tuple[Asset, Blob]], paths: dict[uuid.UUID, list[str]]
) -> list[dict[str, Any]]:
    names = dict(db.execute(select(User.id, User.display_name)).tuples().all())
    album_names: dict[uuid.UUID, list[str]] = {}
    for asset_id, name in db.execute(
        select(AlbumAsset.asset_id, Album.name)
        .join(Album, Album.id == AlbumAsset.album_id)
        .where(Album.space_id == export.space_id)
    ):
        album_names.setdefault(asset_id, []).append(name)
    rows = []
    for asset, blob in items:
        rows.append(
            {
                "paths": paths.get(asset.id, []),
                "sha256": blob.sha256,
                "size_bytes": blob.size_bytes,
                "original_filename": asset.original_filename,
                "taken_at": asset.taken_at_local.isoformat(),
                "taken_at_offset": asset.taken_at_offset,
                "date_source": asset.taken_at_source,
                "kind": asset.kind,
                "review_state": asset.review_state,
                "favorite": asset.is_favorite,
                "albums": sorted(album_names.get(asset.id, [])),
                "description": asset.description,
                "lat": asset.lat,
                "lon": asset.lon,
                "uploaded_by": names.get(asset.uploaded_by) if asset.uploaded_by else None,
                "source": asset.source,
            }
        )
    return rows


def _manifests(rows: list[dict[str, Any]], meta: dict[str, Any]) -> tuple[bytes, bytes]:
    as_json = json.dumps({**meta, "items": rows}, ensure_ascii=False, indent=2).encode()
    out = io.StringIO()
    fields = [
        "paths",
        "sha256",
        "size_bytes",
        "original_filename",
        "taken_at",
        "taken_at_offset",
        "date_source",
        "kind",
        "review_state",
        "favorite",
        "albums",
        "description",
        "lat",
        "lon",
        "uploaded_by",
        "source",
    ]
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, "paths": " | ".join(row["paths"]), "albums": " | ".join(row["albums"])})
    return as_json, ("﻿" + out.getvalue()).encode()  # BOM: Excel lo abre bien con tildes


def build(db: Session, storage: Storage, export_id: uuid.UUID) -> None:
    export = db.get(Export, export_id)
    if export is None or export.state not in ("queued", "running"):
        return
    export.state = "running"
    db.commit()
    params = export.params
    items = _selected_assets(db, export.space_id, params)
    from app.db.models import Space

    space = db.get(Space, export.space_id)
    space_name = space.name if space else "Carrete"
    albums_by_asset: dict[uuid.UUID, list[str]] = {}
    if params["structure"] == "album":
        album_filter = [uuid.UUID(a) for a in params.get("album_ids") or []]
        query = (
            select(AlbumAsset.asset_id, Album.name)
            .join(Album, Album.id == AlbumAsset.album_id)
            .where(Album.space_id == export.space_id)
        )
        if album_filter:
            query = query.where(Album.id.in_(album_filter))
        for asset_id, name in db.execute(query):
            albums_by_asset.setdefault(asset_id, []).append(name)

    names = UniqueNames()
    plan: list[tuple[Path, str, int]] = []
    paths: dict[uuid.UUID, list[str]] = {}
    for asset, blob in items:
        name = file_name(
            asset.original_filename,
            asset.taken_at_local,
            blob.ext,
            normalized=params["naming"] == "normalized",
        )
        for folder in folders_for(
            params["structure"], asset.taken_at_local, sorted(albums_by_asset.get(asset.id, []))
        ):
            path = names.claim(folder, name)
            paths.setdefault(asset.id, []).append(path)
            plan.append((storage.original_path(blob.sha256, blob.ext), path, blob.size_bytes))

    meta = {
        "space": space_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "export_id": str(export.id),
        "options": {k: params[k] for k in ("structure", "naming", "include")},
    }
    manifest_json, manifest_csv = _manifests(_manifest_rows(db, export, items, paths), meta)
    try:
        if params["target"] == "folder":
            files = _to_folder(
                db,
                export,
                plan,
                Path(params["folder"])
                / safe_component(f"Carrete {space_name} {datetime.now(UTC):%Y-%m-%d %H%M}"),
                manifest_json,
                manifest_csv,
            )
        else:
            files = _to_zip(
                db, storage, export, plan, safe_component(space_name), manifest_json, manifest_csv
            )
    except Exception as exc:
        export.state = "failed"
        export.error = str(exc)[:1000]
        export.finished_at = datetime.now(UTC)
        db.commit()
        raise
    export.files = files
    export.state = "ready"
    export.progress = 1.0
    export.finished_at = datetime.now(UTC)
    db.commit()


def export_dir(storage: Storage, export_id: uuid.UUID) -> Path:
    return storage.exports / str(export_id)


def _to_zip(
    db: Session,
    storage: Storage,
    export: Export,
    plan: list[tuple[Path, str, int]],
    base: str,
    manifest_json: bytes,
    manifest_csv: bytes,
) -> list[dict[str, Any]]:
    folder = export_dir(storage, export.id)
    folder.mkdir(parents=True, exist_ok=True)
    limit = int(export.params["volume_bytes"])
    volumes: list[list[tuple[Path, str, int]]] = [[]]
    size = len(manifest_json) + len(manifest_csv)
    for entry in plan:
        if volumes[-1] and size + entry[2] + ZIP_OVERHEAD > limit:
            volumes.append([])
            size = 0
        volumes[-1].append(entry)
        size += entry[2] + ZIP_OVERHEAD
    files: list[dict[str, Any]] = []
    done_bytes = 0
    total = sum(e[2] for e in plan) or 1
    for number, volume in enumerate(volumes, 1):
        name = f"{base}.zip" if len(volumes) == 1 else f"{base} ({number} de {len(volumes)}).zip"
        target = folder / f"{number:03d}.zip"
        partial = target.with_suffix(".partial")
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            if number == 1:
                zf.writestr("carrete-manifest.json", manifest_json)
                zf.writestr("carrete-manifest.csv", manifest_csv)
            for source, arcname, entry_size in volume:
                info = zipfile.ZipInfo.from_file(source, arcname)
                info.compress_type = zipfile.ZIP_STORED
                with source.open("rb") as src, zf.open(info, "w", force_zip64=entry_size > 2**31) as dst:
                    shutil.copyfileobj(src, dst, CHUNK)
                done_bytes += entry_size
                export.progress = min(0.99, done_bytes / total)
            db.commit()
        partial.rename(target)
        files.append({"number": number, "name": name, "size": target.stat().st_size, "items": len(volume)})
    return files


def _to_folder(
    db: Session,
    export: Export,
    plan: list[tuple[Path, str, int]],
    target: Path,
    manifest_json: bytes,
    manifest_csv: bytes,
) -> list[dict[str, Any]]:
    target.mkdir(parents=True, exist_ok=False)
    total = sum(e[2] for e in plan) or 1
    done = 0
    for source, relative, entry_size in plan:
        dest = target / relative
        if not dest.resolve().is_relative_to(target.resolve()):
            raise RuntimeError("Ruta de destino no válida")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        done += entry_size
        export.progress = min(0.99, done / total)
    (target / "carrete-manifest.json").write_bytes(manifest_json)
    (target / "carrete-manifest.csv").write_bytes(manifest_csv)
    db.commit()
    return [{"number": 1, "name": str(target), "size": done, "items": len(plan)}]


def expire(db: Session, storage: Storage, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    old = list(
        db.scalars(
            select(Export).where(Export.expires_at <= now, Export.state.in_(["ready", "failed", "queued"]))
        )
    )
    for export in old:
        shutil.rmtree(export_dir(storage, export.id), ignore_errors=True)
        export.state = "expired"
        export.files = []
    db.commit()
    return len(old)


def get(db: Session, user: User, space_id: uuid.UUID, export_id: uuid.UUID) -> Export:
    acc = spaces.access(db, user, space_id)
    export = db.get(Export, export_id)
    if export is None or export.space_id != space_id:
        raise NotFound("Esa exportación no existe")
    # Cada cual ve las suyas; el propietario, todas las del espacio.
    if export.requested_by != user.id and not acc.can("owner"):
        raise NotFound("Esa exportación no existe")
    return export


def list_for(db: Session, user: User, space_id: uuid.UUID) -> list[Export]:
    acc = spaces.access(db, user, space_id)
    query = select(Export).where(Export.space_id == space_id, Export.state != "expired")
    if not acc.can("owner"):
        query = query.where(Export.requested_by == user.id)
    return list(db.scalars(query.order_by(Export.created_at.desc()).limit(50)))
