"""Fecha de captura.

Se guarda la hora local «de pared» y, si se conoce, el desfase horario. Orden de preferencia:
1. EXIF ``DateTimeOriginal`` (+ ``OffsetTimeOriginal``) o ``creation_time`` del vídeo.
2. Sidecar de Google Takeout.
3. Nombre del fichero (crítico: las fotos de WhatsApp no llevan EXIF).
4. Fecha de modificación que comunica el cliente.
5. Fecha de subida (se marca como dudosa).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from pathlib import PurePath
from zoneinfo import ZoneInfo

MIN_YEAR = 1990


@dataclass(frozen=True)
class CaptureDate:
    local: datetime  # sin zona: hora de pared en el lugar de la captura
    offset_minutes: int | None
    source: str  # exif | video | takeout | filename | mtime | upload

    @property
    def doubtful(self) -> bool:
        return self.source in {"mtime", "upload"}


@dataclass(frozen=True)
class _Pattern:
    regex: re.Pattern[str]
    utc: bool = False  # los nombres de Pixel van en UTC


_D = r"(?P<y>\d{4})[-_.]?(?P<m>\d{2})[-_.]?(?P<d>\d{2})"
_T = r"(?P<H>\d{2})[-_.:h]?(?P<M>\d{2})[-_.:m]?(?P<S>\d{2})"

_PATTERNS: list[_Pattern] = [
    # WhatsApp: IMG-20230415-WA0012.jpg, VID-20230415-WA0003.mp4 (solo fecha)
    _Pattern(re.compile(r"(?:IMG|VID|AUD|PTT|STK|DOC)-(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})-WA\d+", re.I)),
    # WhatsApp de escritorio: «WhatsApp Image 2023-04-15 at 18.30.12.jpeg» (también Video)
    _Pattern(
        re.compile(
            r"WhatsApp (?:Image|Video|Imagen|V[ií]deo|Audio) (?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})"
            r" (?:at|a las) (?P<H>\d{1,2})[.:](?P<M>\d{2})[.:](?P<S>\d{2})",
            re.I,
        )
    ),
    # Google Pixel: PXL_20230415_163012345.jpg (UTC)
    _Pattern(
        re.compile(
            r"PXL_" + r"(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})_(?P<H>\d{2})(?P<M>\d{2})(?P<S>\d{2})", re.I
        ),
        utc=True,
    ),
    # Capturas de macOS en español/inglés
    _Pattern(
        re.compile(
            r"(?:Captura de pantalla|Screen Shot|Screenshot) (?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})"
            r" (?:a las|at) (?P<H>\d{1,2})[.:](?P<M>\d{2})[.:](?P<S>\d{2})",
            re.I,
        )
    ),
    # Android y cámaras: IMG_20230415_183012.jpg, VID_20230415_183012, Screenshot_20230415-183012.png,
    # 20230415_183012.jpg, Screenshot_2023-04-15-18-30-12-123_com.app.jpg, signal-2023-04-15-183012
    _Pattern(re.compile(r"(?<!\d)" + _D + r"[ _T-]" + _T + r"(?!\d{2})")),
    # Solo fecha, inequívoca: 2023-04-15 o 20230415 aislado
    _Pattern(re.compile(r"(?<!\d)(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})(?!\d)")),
    _Pattern(re.compile(r"(?<![\d])(?P<y>(?:19|20)\d{2})(?P<m>\d{2})(?P<d>\d{2})(?!\d)")),
]


def parse_filename(name: str, *, today: date | None = None) -> tuple[datetime, int | None] | None:
    """Fecha y hora deducidas del nombre. Devuelve (hora local, desfase en minutos) o None."""
    stem = PurePath(name.replace("\\", "/")).name
    limit = (today or datetime.now(UTC).date()) + timedelta(days=1)
    for pattern in _PATTERNS:
        for match in pattern.regex.finditer(stem):
            parts = match.groupdict()
            hour = parts.get("H")
            try:
                # Solo fecha (p. ej. WhatsApp): mediodía, para que ningún desfase la cambie de día.
                value = datetime(
                    int(parts["y"]),
                    int(parts["m"]),
                    int(parts["d"]),
                    int(hour) if hour is not None else 12,
                    int(parts.get("M") or 0),
                    int(parts.get("S") or 0),
                )
            except ValueError:
                continue
            if not (value.year >= MIN_YEAR and value.date() <= limit):
                continue
            if pattern.utc:
                return value, 0
            return value, None
    return None


_EXIF_RE = re.compile(r"^(\d{4})[:-](\d{2})[:-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})")
_OFFSET_RE = re.compile(r"([+-])(\d{2}):?(\d{2})$")


def parse_exif_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    match = _EXIF_RE.match(value.strip())
    if not match:
        return None
    y, mo, d, h, mi, se = (int(g) for g in match.groups())
    try:
        parsed = datetime(y, mo, d, h, mi, se)
    except ValueError:
        return None
    return parsed if parsed.year >= MIN_YEAR else None


def parse_offset(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    match = _OFFSET_RE.search(value.strip())
    if not match:
        return None
    sign = -1 if match.group(1) == "-" else 1
    minutes = sign * (int(match.group(2)) * 60 + int(match.group(3)))
    return minutes if -14 * 60 <= minutes <= 14 * 60 else None


def _from_instant(instant: datetime, tz: tzinfo) -> tuple[datetime, int]:
    local = instant.astimezone(tz)
    offset = local.utcoffset() or timedelta(0)
    return local.replace(tzinfo=None), int(offset.total_seconds() // 60)


def deduce(
    *,
    exif_original: object = None,
    exif_offset: object = None,
    video_created_utc: datetime | None = None,
    gps_offset_minutes: int | None = None,
    takeout_timestamp: int | None = None,
    filename: str | None = None,
    client_mtime_ms: int | None = None,
    uploaded_at: datetime,
    default_tz: tzinfo | None = None,
) -> CaptureDate:
    tz = default_tz or ZoneInfo("Europe/Madrid")
    exif = parse_exif_datetime(exif_original)
    if exif is not None:
        return CaptureDate(exif, parse_offset(exif_offset), "exif")
    if video_created_utc is not None and video_created_utc.year >= MIN_YEAR:
        # Los vídeos guardan la hora en UTC. Sin más datos, se muestra en la zona por defecto.
        zone: tzinfo = (
            timezone(timedelta(minutes=gps_offset_minutes)) if gps_offset_minutes is not None else tz
        )
        local, video_offset = _from_instant(video_created_utc, zone)
        return CaptureDate(local, video_offset, "video")
    if takeout_timestamp:
        local, offset = _from_instant(datetime.fromtimestamp(takeout_timestamp, UTC), tz)
        return CaptureDate(local, offset, "takeout")
    if filename:
        parsed = parse_filename(filename, today=uploaded_at.date())
        if parsed is not None:
            value, name_offset = parsed
            if name_offset == 0:  # nombre en UTC (Pixel): se pasa a la zona por defecto
                local, utc_offset = _from_instant(value.replace(tzinfo=UTC), tz)
                return CaptureDate(local, utc_offset, "filename")
            return CaptureDate(value, name_offset, "filename")
    if client_mtime_ms and client_mtime_ms > 0:
        instant = datetime.fromtimestamp(client_mtime_ms / 1000, UTC)
        if instant.year >= MIN_YEAR and instant <= uploaded_at + timedelta(days=1):
            local, offset = _from_instant(instant, tz)
            return CaptureDate(local, offset, "mtime")
    local, offset = _from_instant(uploaded_at, tz)
    return CaptureDate(local, offset, "upload")


_WHATSAPP = re.compile(
    r"(?:^|[^A-Z])(?:IMG|VID|AUD|PTT|STK)-\d{8}-WA\d+|WhatsApp (?:Image|Video|Imagen|V[ií]deo)", re.I
)
_SCREENSHOT = re.compile(r"screenshot|screen[ _]?shot|captura|screen[_ ]?recording|screenrecorder", re.I)
_CAMERA_NAME = re.compile(r"^(?:IMG|VID|PXL|DSC|DSCN|DSCF|MVIMG|PANO|GOPR|GX|DJI|P\d{7}|_DSC)[_-]?\d", re.I)


def deduce_source(filename: str, *, camera: str | None, has_exif_date: bool) -> str:
    """Origen: camera | whatsapp | screenshot | other."""
    name = PurePath(filename.replace("\\", "/")).name
    if _WHATSAPP.search(name):
        return "whatsapp"
    if _SCREENSHOT.search(name):
        return "screenshot"
    if camera or has_exif_date or _CAMERA_NAME.match(name):
        return "camera"
    return "other"
