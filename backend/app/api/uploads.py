"""Subida reanudable con el protocolo tus 1.0 (ADR 0007).

Extensiones: *creation*, *termination*, *checksum* (``sha256`` por trozo, opcional).

- Al crear, el cliente declara nombre, tamaño, SHA-256, fecha de modificación y espacio. Antes de
  aceptar un solo byte se comprueban permisos, tamaño máximo y espacio libre.
- Trozos de como mucho 50 MB por petición (el cliente usa 16 MB).
- Al completarse se recalcula el SHA-256: si no coincide con el declarado, se rechaza y el cliente
  repite. Solo después de guardar, verificar y registrar el original se responde «hecho».
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DB, FullAuth, SettingsDep
from app.config import Settings
from app.db.models import Upload, User
from app.media import sniff
from app.services import assets, spaces
from app.services.errors import Conflict, Invalid, NotFound, ServiceError
from app.storage.files import Storage, sha256_file

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/uploads", tags=["subidas"])

TUS_VERSION = "1.0.0"
MAX_CHUNK = 50 * 1024 * 1024
UPLOAD_TTL = timedelta(hours=48)
TUS_HEADERS = {"Tus-Resumable": TUS_VERSION, "Cache-Control": "no-store"}


class PayloadTooLarge(ServiceError):
    status = 413
    code = "too_large"


class InsufficientStorage(ServiceError):
    status = 507
    code = "disk_full"


class ChecksumMismatch(ServiceError):
    status = 460  # código de la extensión checksum de tus
    code = "checksum_mismatch"


class UnsupportedType(ServiceError):
    status = 415
    code = "unsupported_type"


def storage_dep(settings: SettingsDep) -> Storage:
    return Storage(settings.data_dir)


StorageDep = Annotated[Storage, Depends(storage_dep)]


def _metadata(header: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_pair in (header or "").split(","):
        pair = raw_pair.strip()
        if not pair:
            continue
        key, _, value = pair.partition(" ")
        try:
            result[key] = base64.b64decode(value, validate=True).decode("utf-8") if value else ""
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise Invalid(f"Metadato «{key}» mal codificado", code="bad_metadata") from exc
    return result


def _clean_filename(name: str) -> str:
    # El nombre del usuario nunca se usa como ruta en disco: solo se guarda como texto.
    name = PurePath(name.replace("\\", "/")).name.strip()
    name = "".join(ch for ch in name if ch.isprintable())
    return name[:255] or "sin-nombre"


@router.options("", include_in_schema=False)
def tus_options(settings: SettingsDep) -> Response:
    return Response(
        status_code=204,
        headers={
            **TUS_HEADERS,
            "Tus-Version": TUS_VERSION,
            "Tus-Extension": "creation,termination,checksum",
            "Tus-Max-Size": str(settings.max_upload_bytes),
            "Tus-Checksum-Algorithm": "sha256",
        },
    )


@router.post("", status_code=201)
def create_upload(
    current: FullAuth,
    db: DB,
    settings: SettingsDep,
    storage: StorageDep,
    upload_length: Annotated[int, Header(ge=1)],
    upload_metadata: Annotated[str | None, Header()] = None,
    tus_resumable: Annotated[str | None, Header()] = None,
) -> Response:
    if tus_resumable != TUS_VERSION:
        raise Invalid("Versión de tus no admitida", code="tus_version")
    meta = _metadata(upload_metadata)
    try:
        space_id = uuid.UUID(meta.get("space_id", ""))
    except ValueError as exc:
        raise Invalid("Falta el espacio de destino", code="no_space") from exc
    spaces.access(db, current.user, space_id, "collaborator")

    sha = meta.get("sha256", "").lower()
    if len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha):
        raise Invalid("Falta el SHA-256 del fichero", code="no_checksum")
    if upload_length > settings.max_upload_bytes:
        raise PayloadTooLarge(
            f"El fichero supera el tamaño máximo ({settings.max_upload_bytes // 1024**3} GB)",
            max_bytes=settings.max_upload_bytes,
        )
    if storage.free_bytes() - upload_length < settings.min_free_bytes:
        raise InsufficientStorage("No queda espacio libre suficiente en el servidor. Avisa al administrador.")
    if sha in assets.present_hashes(db, space_id, [sha]):
        raise Conflict("Ya estaba en este espacio", code="duplicate")

    mtime = meta.get("mtime")
    album = meta.get("album_id")
    upload = Upload(
        user_id=current.user.id,
        space_id=space_id,
        album_id=uuid.UUID(album) if album else None,
        filename=_clean_filename(meta.get("filename", "")),
        relative_path=(meta.get("relative_path") or None),
        declared_size=upload_length,
        declared_sha256=sha,
        client_mtime_ms=int(mtime) if mtime and mtime.isdigit() else None,
        uploaded_via="android" if current.session.kind == "device" else "web",
        expires_at=datetime.now(UTC) + UPLOAD_TTL,
    )
    db.add(upload)
    db.flush()
    storage.uploads.mkdir(parents=True, exist_ok=True)
    storage.upload_path(upload.id).touch()
    db.commit()
    return Response(
        status_code=201,
        headers={**TUS_HEADERS, "Location": f"/api/v1/uploads/{upload.id}", "Upload-Offset": "0"},
    )


def _own_upload(db: Session, user: User, upload_id: uuid.UUID) -> Upload:
    upload = db.get(Upload, upload_id)
    if upload is None or upload.user_id != user.id or upload.state != "receiving":
        raise NotFound("Esa subida no existe o ya terminó", code="upload_gone")
    if upload.expires_at <= datetime.now(UTC):
        raise NotFound("La subida caducó; vuelve a empezar", code="upload_gone")
    return upload


@router.head("/{upload_id}")
def upload_status(upload_id: uuid.UUID, current: FullAuth, db: DB) -> Response:
    upload = _own_upload(db, current.user, upload_id)
    return Response(
        status_code=200,
        headers={
            **TUS_HEADERS,
            "Upload-Offset": str(upload.offset),
            "Upload-Length": str(upload.declared_size),
        },
    )


@router.patch("/{upload_id}")
async def upload_chunk(
    upload_id: uuid.UUID,
    request: Request,
    current: FullAuth,
    db: DB,
    settings: SettingsDep,
    storage: StorageDep,
    upload_offset: Annotated[int, Header(ge=0)],
    content_type: Annotated[str | None, Header()] = None,
    upload_checksum: Annotated[str | None, Header()] = None,
) -> Response:
    if content_type != "application/offset+octet-stream":
        raise UnsupportedType(
            "Content-Type debe ser application/offset+octet-stream", code="bad_content_type"
        )
    upload = await run_in_threadpool(_own_upload, db, current.user, upload_id)
    if upload_offset != upload.offset:
        raise Conflict(
            "El desplazamiento no coincide; consulta el estado y reanuda",
            code="offset_mismatch",
            offset=upload.offset,
        )

    expected_digest: bytes | None = None
    if upload_checksum:
        algorithm, _, value = upload_checksum.partition(" ")
        if algorithm != "sha256":
            raise Invalid("Algoritmo de suma de comprobación no admitido", code="bad_checksum_algorithm")
        expected_digest = base64.b64decode(value)

    path = storage.upload_path(upload.id)
    digest = hashlib.sha256()
    received = 0
    remaining = upload.declared_size - upload.offset
    with path.open("r+b") as f:
        f.seek(upload.offset)
        f.truncate()
        async for chunk in request.stream():
            if not chunk:
                continue
            received += len(chunk)
            if received > MAX_CHUNK:
                f.truncate(upload.offset)
                raise PayloadTooLarge("Trozo demasiado grande (máximo 50 MB por petición)")
            if received > remaining:
                f.truncate(upload.offset)
                raise Invalid("Se han enviado más bytes de los declarados", code="too_many_bytes")
            f.write(chunk)
            if expected_digest is not None:
                digest.update(chunk)
        if expected_digest is not None and digest.digest() != expected_digest:
            f.truncate(upload.offset)
            raise ChecksumMismatch("El trozo llegó dañado; se repetirá")

    upload.offset += received
    headers = {**TUS_HEADERS, "Upload-Offset": str(upload.offset)}
    if upload.offset < upload.declared_size:
        await run_in_threadpool(db.commit)
        return Response(status_code=204, headers=headers)

    asset_id, duplicate = await run_in_threadpool(_finalize, db, settings, storage, upload)
    headers |= {"Carrete-Asset-Id": str(asset_id), "Carrete-Duplicate": "1" if duplicate else "0"}
    return Response(status_code=204, headers=headers)


def _finalize(db: Session, settings: Settings, storage: Storage, upload: Upload) -> tuple[uuid.UUID, bool]:
    """Comprueba el fichero completo y lo convierte en original. Invariante 3."""
    path = storage.upload_path(upload.id)
    actual = sha256_file(path)
    if actual != upload.declared_sha256:
        upload.state = "failed"
        db.commit()
        path.unlink(missing_ok=True)
        raise ChecksumMismatch(
            "El fichero llegó distinto de como salió; vuelve a subirlo", code="file_mismatch"
        )
    with path.open("rb") as f:
        file_type = sniff.detect(f.read(sniff.HEADER_BYTES))
    if file_type is None:
        upload.state = "failed"
        db.commit()
        path.unlink(missing_ok=True)
        raise UnsupportedType(
            f"«{upload.filename}» no es una foto ni un vídeo admitido "
            "(JPEG, PNG, WebP, GIF, HEIC, AVIF, MP4, MOV, 3GP, WebM, MKV)"
        )
    storage.commit_original(path, actual, file_type.ext)
    registered = assets.register(
        db,
        space_id=upload.space_id,
        user_id=upload.user_id,
        sha256=actual,
        size=upload.declared_size,
        file_type=file_type,
        filename=upload.filename,
        relative_path=upload.relative_path,
        client_mtime_ms=upload.client_mtime_ms,
        uploaded_via=upload.uploaded_via,
    )
    if upload.album_id is not None:
        from app.services import albums

        albums.add_on_upload(db, upload.space_id, upload.album_id, registered.asset.id)
    upload.state = "done"
    upload.asset_id = registered.asset.id
    db.commit()
    return registered.asset.id, registered.duplicate


@router.delete("/{upload_id}", status_code=204)
def cancel_upload(upload_id: uuid.UUID, current: FullAuth, db: DB, storage: StorageDep) -> Response:
    upload = _own_upload(db, current.user, upload_id)
    upload.state = "cancelled"
    storage.upload_path(upload.id).unlink(missing_ok=True)
    db.commit()
    return Response(status_code=204, headers=TUS_HEADERS)


def purge_expired(db: Session, storage: Storage) -> int:
    """Borra las subidas a medias abandonadas (más de 48 h). La llama el worker."""
    expired = list(
        db.scalars(select(Upload).where(Upload.state == "receiving", Upload.expires_at <= datetime.now(UTC)))
    )
    for upload in expired:
        upload.state = "cancelled"
        storage.upload_path(upload.id).unlink(missing_ok=True)
    db.commit()
    return len(expired)
