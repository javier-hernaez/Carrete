"""Importación desde un ZIP o desde una carpeta del servidor.

Todo pasa por la misma vía que una subida: copia a un temporal calculando el SHA-256 → tipo real por
contenido → original inmutable → alta en el espacio (sin duplicar) → procesado en el worker.

Protección del ZIP (fichero no fiable):
- Nunca se extrae a disco por su ruta: cada entrada se lee como flujo y se guarda con un nombre propio,
  así que ``../`` o rutas absolutas no pueden escribir fuera de su sitio.
- Límite de entradas, de tamaño por entrada y de tamaño total (según el espacio libre).
- Proporción de compresión sospechosa (bomba de compresión) → la entrada se descarta.
- Se cuentan los bytes reales: una entrada que descomprime más de lo que declara se corta.

Google Takeout guarda la fecha y la ubicación en ficheros ``.json`` aparte (``title``,
``photoTakenTime.timestamp``, ``geoData``): se emparejan por carpeta y nombre original.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import IO, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Album, Import, Membership, Space, User
from app.media import sniff
from app.services import albums, assets, audit
from app.storage.files import CHUNK, Storage

log = logging.getLogger(__name__)

MAX_ENTRIES = 200_000
MAX_RATIO = 200  # descomprimido / comprimido
RATIO_MIN_BYTES = 20 * 1024 * 1024
MAX_SIDECAR = 1024 * 1024
IGNORED = ("__MACOSX/", ".DS_Store", "Thumbs.db", "desktop.ini")


class EntryTooBig(Exception):
    pass


@dataclass
class Counts:
    imported: int = 0
    duplicates: int = 0
    skipped: int = 0
    unsupported: int = 0
    suspicious: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "imported": self.imported,
            "duplicates": self.duplicates,
            "skipped": self.skipped,
            "unsupported": self.unsupported,
            "suspicious": self.suspicious,
            "errors": self.errors[:20],
        }


@dataclass
class Takeout:
    timestamp: int | None = None
    lat: float | None = None
    lon: float | None = None


def _copy_hashing(src: IO[bytes], dest: Path, limit: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    written = 0
    with dest.open("wb") as out:
        while chunk := src.read(CHUNK):
            written += len(chunk)
            if written > limit:
                raise EntryTooBig
            digest.update(chunk)
            out.write(chunk)
    return digest.hexdigest(), written


def ingest(
    db: Session,
    storage: Storage,
    *,
    space_id: uuid.UUID,
    user_id: uuid.UUID,
    stream: IO[bytes],
    filename: str,
    relative_path: str | None,
    limit: int,
    mtime_ms: int | None = None,
    album_id: uuid.UUID | None = None,
    takeout: Takeout | None = None,
    counts: Counts,
) -> uuid.UUID | None:
    """Guarda un fichero como original y lo da de alta. Devuelve el elemento, o None si se descartó."""
    storage.uploads.mkdir(parents=True, exist_ok=True)
    temp = storage.uploads / f"import-{uuid.uuid4()}.part"
    try:
        try:
            sha, size = _copy_hashing(stream, temp, limit)
        except EntryTooBig:
            counts.suspicious += 1
            return None
        with temp.open("rb") as f:
            file_type = sniff.detect(f.read(sniff.HEADER_BYTES))
        if file_type is None:
            counts.unsupported += 1
            return None
        storage.commit_original(temp, sha, file_type.ext)
        registered = assets.register(
            db,
            space_id=space_id,
            user_id=user_id,
            sha256=sha,
            size=size,
            file_type=file_type,
            filename=filename,
            relative_path=relative_path,
            client_mtime_ms=mtime_ms,
            uploaded_via="import",
        )
        if registered.duplicate:
            counts.duplicates += 1
        else:
            counts.imported += 1
            if takeout and (takeout.timestamp or takeout.lat is not None):
                registered.asset.metadata_json = {
                    **registered.asset.metadata_json,
                    "takeout": {"timestamp": takeout.timestamp, "lat": takeout.lat, "lon": takeout.lon},
                }
        if album_id is not None:
            album = db.get(Album, album_id)
            if album is not None and album.space_id == space_id:
                albums.add_assets(db, album, [registered.asset.id], user_id)
        return registered.asset.id
    finally:
        temp.unlink(missing_ok=True)


# --- ZIP ---------------------------------------------------------------------------------------------


def _is_ignored(name: str) -> bool:
    return (
        name.endswith("/")
        or any(part in name for part in IGNORED)
        or PurePosixPath(name).name.startswith("._")
    )


def parse_takeout(data: bytes) -> tuple[str, Takeout] | None:
    try:
        meta = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(meta, dict) or not isinstance(meta.get("title"), str):
        return None
    taken = meta.get("photoTakenTime") or meta.get("creationTime") or {}
    raw = taken.get("timestamp") if isinstance(taken, dict) else None
    timestamp = int(raw) if isinstance(raw, (str, int)) and str(raw).isdigit() else None
    geo = meta.get("geoData") or {}
    lat = geo.get("latitude") if isinstance(geo, dict) else None
    lon = geo.get("longitude") if isinstance(geo, dict) else None
    has_geo = isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and (lat, lon) != (0, 0)
    if not has_geo:
        return meta["title"], Takeout(timestamp)
    assert isinstance(lat, (int, float)) and isinstance(lon, (int, float))
    return meta["title"], Takeout(timestamp, float(lat), float(lon))


def _entries(zf: zipfile.ZipFile, counts: Counts) -> Iterator[zipfile.ZipInfo]:
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise ValueError(f"El ZIP tiene demasiadas entradas ({len(infos)})")
    for info in infos:
        if _is_ignored(info.filename):
            continue
        yield info


def import_zip(
    db: Session,
    storage: Storage,
    zip_path: Path,
    *,
    space_id: uuid.UUID,
    user_id: uuid.UUID,
    max_entry_bytes: int,
    max_total_bytes: int,
    album_id: uuid.UUID | None = None,
) -> Counts:
    counts = Counts()
    with zipfile.ZipFile(zip_path) as zf:
        entries = list(_entries(zf, counts))
        sidecars: dict[tuple[str, str], Takeout] = {}
        for info in entries:
            if info.filename.lower().endswith(".json") and info.file_size <= MAX_SIDECAR:
                parsed = parse_takeout(zf.read(info))
                if parsed:
                    folder = str(PurePosixPath(info.filename).parent)
                    sidecars[(folder, parsed[0].lower())] = parsed[1]
        total = 0
        for info in entries:
            name = PurePosixPath(info.filename.replace("\\", "/"))
            if name.suffix.lower() == ".json":
                continue
            if info.file_size > max_entry_bytes:
                counts.skipped += 1
                continue
            ratio = info.file_size / max(info.compress_size, 1)
            if info.file_size > RATIO_MIN_BYTES and ratio > MAX_RATIO:
                counts.suspicious += 1
                continue
            total += info.file_size
            if total > max_total_bytes:
                counts.errors.append("Se ha parado: no queda espacio libre suficiente")
                break
            mtime = (
                int(datetime(*info.date_time, tzinfo=UTC).timestamp() * 1000)
                if info.date_time[0] >= 1990
                else None
            )
            folder = str(name.parent)
            takeout = sidecars.get((folder, name.name.lower()))
            try:
                with zf.open(info) as stream:
                    ingest(
                        db,
                        storage,
                        space_id=space_id,
                        user_id=user_id,
                        stream=stream,
                        filename=name.name,
                        relative_path=str(name) if folder != "." else None,
                        limit=max(info.file_size, 1),
                        mtime_ms=mtime,
                        album_id=album_id,
                        takeout=takeout,
                        counts=counts,
                    )
                db.commit()
            except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
                db.rollback()
                counts.errors.append(f"{name.name}: {exc}")
    return counts


# --- Carpeta del servidor ----------------------------------------------------------------------------


def import_folder(
    db: Session,
    storage: Storage,
    folder: Path,
    *,
    space_id: uuid.UUID,
    user_id: uuid.UUID,
    max_entry_bytes: int,
    albums_from_folders: bool = False,
    progress: Any = None,
) -> Counts:
    counts = Counts()
    album_ids: dict[str, uuid.UUID] = {}
    user = db.get(User, user_id)
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and not _is_ignored(str(p))):
        relative = path.relative_to(folder)
        if path.suffix.lower() == ".json":
            continue
        if path.stat().st_size > max_entry_bytes:
            counts.skipped += 1
            continue
        album_id = None
        if albums_from_folders and len(relative.parts) > 1 and user is not None:
            top = relative.parts[0]
            if top not in album_ids:
                existing = db.scalar(select(Album).where(Album.space_id == space_id, Album.name == top))
                album = existing or albums.create(db, space_id, user, top, None, audit.RequestInfo())
                album_ids[top] = album.id
            album_id = album_ids[top]
        with path.open("rb") as stream:
            ingest(
                db,
                storage,
                space_id=space_id,
                user_id=user_id,
                stream=stream,
                filename=path.name,
                relative_path=str(relative),
                limit=path.stat().st_size,
                mtime_ms=int(path.stat().st_mtime * 1000),
                album_id=album_id,
                counts=counts,
            )
        db.commit()
        if progress is not None:
            progress(counts)
    return counts


def resolve_space(db: Session, value: str) -> Space:
    try:
        space = db.get(Space, uuid.UUID(value))
    except ValueError:
        space = db.scalar(select(Space).where(Space.name == value))
    if space is None:
        raise ValueError(f"No existe el espacio «{value}»")
    return space


def default_owner(db: Session, space_id: uuid.UUID) -> uuid.UUID:
    owner = db.scalar(
        select(Membership.user_id).where(Membership.space_id == space_id, Membership.role == "owner").limit(1)
    )
    if owner is None:
        raise ValueError("El espacio no tiene propietario")
    return owner


def run_import(
    db: Session, storage: Storage, import_id: uuid.UUID, zip_path: Path, max_entry_bytes: int, min_free: int
) -> None:
    record = db.get(Import, import_id)
    if record is None or record.state not in ("queued", "running") or record.user_id is None:
        return
    record.state = "running"
    db.commit()
    try:
        counts = import_zip(
            db,
            storage,
            zip_path,
            space_id=record.space_id,
            user_id=record.user_id,
            max_entry_bytes=max_entry_bytes,
            max_total_bytes=max(0, storage.free_bytes() - min_free),
            album_id=record.album_id,
        )
    except (zipfile.BadZipFile, ValueError) as exc:
        db.rollback()
        record = db.get(Import, import_id)
        assert record is not None
        record.state = "failed"
        record.error = str(exc)[:500]
        record.finished_at = datetime.now(UTC)
        db.commit()
        zip_path.unlink(missing_ok=True)
        return
    record.state = "done"
    record.counts = counts.as_dict()
    record.finished_at = datetime.now(UTC)
    audit.record(
        db,
        "asset.uploaded",
        actor_id=record.user_id,
        space_id=record.space_id,
        detail={
            "uploaded": counts.imported,
            "duplicates": counts.duplicates,
            "failed": counts.unsupported + counts.suspicious + counts.skipped,
            "source": "zip",
        },
    )
    db.commit()
    zip_path.unlink(missing_ok=True)
