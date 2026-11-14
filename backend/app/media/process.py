"""Procesado de un elemento recién subido. Lo ejecuta el ``worker``.

validar tipo real → metadatos → fecha y origen → derivados → ThumbHash y huella perceptual.

El ``worker`` trata ficheros no fiables con bibliotecas en C, así que:
- corre sin red, sin privilegios y con el sistema de ficheros de solo lectura (docker-compose.yml);
- se lee la cabecera antes de descodificar y se rechazan imágenes de más de ``MAX_PIXELS``;
- ``ffmpeg``/``ffprobe``/``exiftool`` tienen tiempo máximo y prioridad baja;
- un fichero que no se puede procesar queda guardado y marcado, nunca se descarta.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Asset, Blob
from app.media import dates, sniff
from app.media.thumbhash import encode_b64, rgba_to_thumbhash
from app.storage.files import Storage

log = logging.getLogger(__name__)

MAX_PIXELS = 250_000_000  # 250 MP: más que cualquier cámara; frena bombas de descompresión
MAX_VIDEO_SECONDS = 4 * 3600
THUMB_SIZE = 320
PREVIEW_SIZE = 2048
VIDEO_PREVIEW_HEIGHT = 720
TOOL_TIMEOUT = 120
TRANSCODE_TIMEOUT = 3 * 3600

# Lo que reproducen todos los navegadores sin conversión.
PLAYABLE = {("mp4", "h264"), ("webm", "vp8"), ("webm", "vp9"), ("webm", "av1"), ("mp4", "av1")}


class MediaError(Exception):
    pass


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise MediaError(f"Falta la herramienta {name}")
    return path


def _run(args: list[str], timeout: int = TOOL_TIMEOUT) -> bytes:
    try:
        result = subprocess.run(  # noqa: S603  # argumentos sin shell; la ruta del fichero es nuestra
            [_tool("nice"), "-n", "10", *args], capture_output=True, timeout=timeout, check=True
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"{Path(args[0]).name} tardó demasiado") from exc
    except subprocess.CalledProcessError as exc:
        raise MediaError(f"{Path(args[0]).name} falló: {exc.stderr.decode(errors='replace')[-300:]}") from exc
    return result.stdout


# --- Metadatos -----------------------------------------------------------------------------------------


EXIF_TAGS = [
    "-EXIF:DateTimeOriginal",
    "-EXIF:OffsetTimeOriginal",
    "-EXIF:CreateDate",
    "-XMP:DateTimeOriginal",
    "-Keys:CreationDate",
    "-QuickTime:CreateDate",
    "-GPSLatitude",
    "-GPSLongitude",
    "-Make",
    "-Model",
    "-Orientation",
    "-ImageWidth",
    "-ImageHeight",
    "-Duration",
]


def read_metadata(path: Path) -> dict[str, Any]:
    out = _run(
        [_tool("exiftool"), "-j", "-n", "-G1", "-charset", "filename=utf8", *EXIF_TAGS, "--", str(path)]
    )
    data = json.loads(out or b"[{}]")
    return data[0] if data else {}


def _first(meta: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = meta.get(key)
        if value not in (None, "", "0000:00:00 00:00:00"):
            return value
    return None


def probe_video(path: Path) -> dict[str, Any]:
    out = _run(
        [_tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    )
    data: dict[str, Any] = json.loads(out or b"{}")
    return data


@dataclass
class VideoInfo:
    duration_ms: int | None = None
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    container: str | None = None
    has_audio: bool = False
    rotation: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def video_info(probe: dict[str, Any], ext: str) -> VideoInfo:
    info = VideoInfo(container={"mov": "mov", "mp4": "mp4", "webm": "webm"}.get(ext, ext))
    duration = probe.get("format", {}).get("duration")
    if duration:
        info.duration_ms = int(float(duration) * 1000)
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "audio":
            info.has_audio = True
        if stream.get("codec_type") == "video" and info.codec is None:
            info.codec = stream.get("codec_name")
            info.width, info.height = stream.get("width"), stream.get("height")
            rotation = stream.get("tags", {}).get("rotate")
            for side in stream.get("side_data_list", []):
                rotation = side.get("rotation", rotation)
            try:
                info.rotation = int(float(rotation or 0)) % 360
            except ValueError:
                info.rotation = 0
    if info.rotation in (90, 270) and info.width and info.height:
        info.width, info.height = info.height, info.width
    return info


def _quicktime_utc(value: Any) -> datetime | None:
    parsed = dates.parse_exif_datetime(value)
    return parsed.replace(tzinfo=UTC) if parsed else None


# --- Imágenes ------------------------------------------------------------------------------------------


def _vips() -> Any:
    import pyvips

    pyvips.cache_set_max(0)
    return pyvips


def make_image_derivatives(source: Path, out_dir: Path) -> tuple[int, int, str, int]:
    """Vista previa, miniatura, ThumbHash y dHash. Devuelve (ancho, alto, thumbhash, dhash)."""
    vips = _vips()
    header = vips.Image.new_from_file(str(source), access="sequential")
    if header.width * header.height > MAX_PIXELS:
        raise MediaError(f"Imagen demasiado grande ({header.width}×{header.height})")
    # thumbnail() aplica la orientación EXIF y no descodifica más de lo necesario.
    preview = vips.Image.thumbnail(str(source), PREVIEW_SIZE, height=PREVIEW_SIZE, size="down")
    preview = _to_srgb(preview).copy_memory()  # se reutiliza: no puede seguir siendo un flujo secuencial
    out_dir.mkdir(parents=True, exist_ok=True)
    _save_webp(preview, out_dir / "preview.webp", quality=82)
    thumb = preview.thumbnail_image(THUMB_SIZE, height=THUMB_SIZE, size="down")
    _save_webp(thumb, out_dir / "thumb.webp", quality=75)
    return preview.width, preview.height, compute_thumbhash(thumb), compute_dhash(thumb)


def _to_srgb(image: Any) -> Any:
    if image.interpretation not in ("srgb", "b-w"):
        image = image.colourspace("srgb")
    if image.bands == 2:  # gris con alfa
        image = image.colourspace("srgb")
    return image


def _save_webp(image: Any, path: Path, *, quality: int) -> None:
    tmp = path.with_suffix(".tmp.webp")
    image.webpsave(str(tmp), Q=quality, strip=True)
    tmp.replace(path)


def compute_thumbhash(image: Any) -> str:
    small = image.thumbnail_image(100, height=100, size="down")
    if small.bands == 1:
        small = small.colourspace("srgb")
    if small.bands == 3:
        small = small.bandjoin(255)
    small = small.cast("uchar")
    return encode_b64(rgba_to_thumbhash(small.width, small.height, bytes(small.write_to_memory())))


def compute_dhash(image: Any) -> int:
    """Huella perceptual dHash de 64 bits, como entero con signo para PostgreSQL."""
    gray = image.colourspace("b-w") if image.bands >= 3 else image
    if gray.bands > 1:
        gray = gray.extract_band(0)
    small = gray.thumbnail_image(9, height=8, size="force").cast("uchar")
    pixels = bytes(small.write_to_memory())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (1 if pixels[y * 9 + x] > pixels[y * 9 + x + 1] else 0)
    return bits - (1 << 64) if bits >= 1 << 63 else bits


def hamming(a: int, b: int) -> int:
    return ((a ^ b) & 0xFFFFFFFFFFFFFFFF).bit_count()


# --- Vídeo ---------------------------------------------------------------------------------------------


def make_video_derivatives(source: Path, out_dir: Path, info: VideoInfo) -> tuple[str, int, bool]:
    if info.duration_ms and info.duration_ms > MAX_VIDEO_SECONDS * 1000:
        raise MediaError("Vídeo demasiado largo para procesarlo")
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="carrete-") as tmp:
        poster = Path(tmp) / "poster.png"
        seek = min(1.0, (info.duration_ms or 0) / 2000)
        _run(
            [
                _tool("ffmpeg"),
                "-v",
                "error",
                "-ss",
                f"{seek:.2f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-y",
                str(poster),
            ]
        )
        if not poster.exists():  # vídeo muy corto: primer fotograma
            _run([_tool("ffmpeg"), "-v", "error", "-i", str(source), "-frames:v", "1", "-y", str(poster)])
        _, _, thash, dhash = make_image_derivatives(poster, out_dir)

    playable = (info.container, info.codec) in PLAYABLE and info.rotation == 0
    if playable:
        return thash, dhash, False
    target = out_dir / "video.mp4"
    tmp_target = out_dir / "video.tmp.mp4"
    # El lado corto a 720 px como mucho, sin ampliar, conservando la proporción.
    side = VIDEO_PREVIEW_HEIGHT
    scale = f"scale=w='if(gt(iw,ih),-2,min({side},iw))':h='if(gt(iw,ih),min({side},ih),-2)'"
    args = [
        _tool("ffmpeg"),
        "-v",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-vf",
        scale,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "26",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-threads",
        "2",
        "-y",
        str(tmp_target),
    ]
    _run(args, timeout=TRANSCODE_TIMEOUT)
    tmp_target.replace(target)
    return thash, dhash, True


# --- Tarea ---------------------------------------------------------------------------------------------


def process_asset(db: Session, storage: Storage, asset_id: uuid.UUID) -> None:
    asset = db.get(Asset, asset_id)
    if asset is None:
        return  # eliminado mientras esperaba: nada que hacer
    blob = db.get(Blob, asset.blob_id)
    assert blob is not None
    source = storage.original_path(blob.sha256, blob.ext)
    if not source.exists():
        raise MediaError("No se encuentra el original en disco")

    with source.open("rb") as f:
        if sniff.detect(f.read(sniff.HEADER_BYTES)) is None:
            raise MediaError("Tipo de fichero no admitido")

    meta = read_metadata(source)
    out_dir = storage.derivative_dir(blob.sha256)
    camera = (
        " ".join(
            str(v)
            for v in (
                _first(meta, "IFD0:Make", "QuickTime:Make", "Keys:Make"),
                _first(meta, "IFD0:Model", "QuickTime:Model", "Keys:Model"),
            )
            if v
        )
        or None
    )
    lat = _first(meta, "Composite:GPSLatitude", "GPS:GPSLatitude", "Keys:GPSCoordinates")
    lon = _first(meta, "Composite:GPSLongitude", "GPS:GPSLongitude")

    exif_original = _first(meta, "ExifIFD:DateTimeOriginal", "XMP-exif:DateTimeOriginal", "Keys:CreationDate")
    exif_offset = _first(meta, "ExifIFD:OffsetTimeOriginal")
    if (
        exif_offset is None
        and isinstance(exif_original, str)
        and dates.parse_offset(exif_original) is not None
    ):
        exif_offset = exif_original  # Keys:CreationDate de Apple lleva el desfase incluido
    video_created = _quicktime_utc(_first(meta, "QuickTime:CreateDate"))

    if asset.kind == "video":
        info = video_info(probe_video(source), blob.ext)
        if out_dir.joinpath("thumb.webp").exists() and (
            out_dir.joinpath("video.mp4").exists() or (info.container, info.codec) in PLAYABLE
        ):
            from app.media import cache

            thash, dhash, has_video = cache.read(out_dir)
        else:
            thash, dhash, has_video = make_video_derivatives(source, out_dir, info)
        asset.width, asset.height = info.width, info.height
        asset.duration_ms = info.duration_ms
        asset.video_codec = info.codec
        asset.has_preview_video = has_video
    else:
        width, height, thash, dhash = make_image_derivatives(source, out_dir)
        full_w, full_h = (
            _first(meta, "File:ImageWidth", "EXIF:ImageWidth", "ExifIFD:ExifImageWidth"),
            _first(meta, "File:ImageHeight", "EXIF:ImageHeight", "ExifIFD:ExifImageHeight"),
        )
        orientation = _first(meta, "IFD0:Orientation")
        asset.orientation = int(orientation) if isinstance(orientation, (int, float)) else None
        if isinstance(full_w, (int, float)) and isinstance(full_h, (int, float)):
            w, h = int(full_w), int(full_h)
            if asset.orientation in (5, 6, 7, 8):
                w, h = h, w
            asset.width, asset.height = w, h
        else:
            asset.width, asset.height = width, height

    from app.media import cache

    cache.write(out_dir, thash, dhash, asset.has_preview_video)
    asset.thumbhash = thash
    asset.phash = dhash
    asset.camera = camera[:200] if camera else None
    takeout = asset.metadata_json.get("takeout") if isinstance(asset.metadata_json, dict) else None
    takeout = takeout if isinstance(takeout, dict) else {}
    if (
        not (isinstance(lat, (int, float)) and isinstance(lon, (int, float)))
        and takeout.get("lat") is not None
    ):
        lat, lon = takeout.get("lat"), takeout.get("lon")
    if (
        isinstance(lat, (int, float))
        and isinstance(lon, (int, float))
        and (lat, lon) != (0, 0)
        and -90 <= lat <= 90
        and -180 <= lon <= 180
    ):
        asset.lat, asset.lon = float(lat), float(lon)
    from app.services.geo import assign_place

    assign_place(asset)

    # La fecha solo se recalcula si nadie la ha corregido a mano.
    if asset.taken_at_source != "manual":
        found = dates.deduce(
            exif_original=exif_original,
            exif_offset=exif_offset,
            video_created_utc=video_created,
            takeout_timestamp=takeout.get("timestamp") if isinstance(takeout.get("timestamp"), int) else None,
            filename=asset.original_filename,
            client_mtime_ms=asset.client_mtime_ms,
            uploaded_at=asset.created_at,
        )
        asset.taken_at_local, asset.taken_at_offset, asset.taken_at_source = (
            found.local,
            found.offset_minutes,
            found.source,
        )
    asset.source = dates.deduce_source(
        asset.original_filename, camera=camera, has_exif_date=exif_original is not None
    )
    asset.metadata_json = {
        k: v for k, v in meta.items() if k != "SourceFile" and isinstance(v, (str, int, float))
    }
    asset.processing_state = "ready"
    asset.processing_error = None
    db.flush()
    from app.config import get_settings
    from app.services.duplicates import detect_for

    detect_for(db, asset, get_settings().duplicate_distance)


def environment_ready() -> list[str]:
    """Herramientas que faltan (para /readyz del worker y las pruebas)."""
    missing = [name for name in ("exiftool", "ffmpeg", "ffprobe", "nice") if shutil.which(name) is None]
    try:
        _vips()
    except Exception:  # pragma: no cover
        missing.append("libvips")
    return missing


os.environ.setdefault("VIPS_CONCURRENCY", "2")
