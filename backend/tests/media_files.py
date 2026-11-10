"""Generador de fotos y vídeos sintéticos para las pruebas (nunca fotos reales)."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def make_jpeg(
    path: Path,
    *,
    color: tuple[int, int, int] = (200, 80, 40),
    size: tuple[int, int] = (640, 480),
    exif_date: str | None = None,
    offset: str | None = None,
    gps: tuple[float, float] | None = None,
    make: str | None = None,
    pattern: int = 0,
) -> Path:
    import pyvips

    w, h = size
    base = pyvips.Image.black(w, h, bands=3) + list(color)
    # Un degradado distinto por «pattern» para que las fotos no sean idénticas a ojo.
    grad = pyvips.Image.xyz(w, h)[0] * (255 / max(w, 1))
    image = (base * 0.6 + grad.bandjoin([grad, grad]) * (0.4 if pattern % 2 == 0 else -0.2)).cast("uchar")
    image.jpegsave(str(path), Q=85)
    tags = []
    if exif_date:
        tags.append(f"-DateTimeOriginal={exif_date}")
    if offset:
        tags.append(f"-OffsetTimeOriginal={offset}")
    if gps:
        lat, lon = gps
        tags += [
            f"-GPSLatitude={abs(lat)}",
            f"-GPSLatitudeRef={'N' if lat >= 0 else 'S'}",
            f"-GPSLongitude={abs(lon)}",
            f"-GPSLongitudeRef={'E' if lon >= 0 else 'W'}",
        ]
    if make:
        tags += [f"-Make={make}", "-Model=Prueba"]
    if tags:
        subprocess.run(["exiftool", "-q", "-overwrite_original", *tags, str(path)], check=True)
    return path


def make_video(
    path: Path, *, codec: str = "libx264", seconds: float = 1.0, creation: str | None = None
) -> Path:
    args = [
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=320x240:rate=10:duration={seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={seconds}",
        "-c:v",
        codec,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
    ]
    if codec == "libx265":
        args += ["-tag:v", "hvc1", "-x265-params", "log-level=error"]
    if creation:
        args += ["-metadata", f"creation_time={creation}"]
    subprocess.run([*args, "-y", str(path)], check=True)
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
