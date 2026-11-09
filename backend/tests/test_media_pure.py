"""Partes puras del procesado de medios: tipo por contenido, fechas, origen y ThumbHash."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.media import dates, sniff
from app.media.thumbhash import rgba_to_thumbhash

MADRID = ZoneInfo("Europe/Madrid")
UPLOADED = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (b"\xff\xd8\xff\xe0\x00\x10JFIF", ("photo", "jpg")),
        (b"\x89PNG\r\n\x1a\n\x00\x00", ("photo", "png")),
        (b"GIF89a\x01\x00", ("photo", "gif")),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", ("photo", "webp")),
        (b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic", ("photo", "heic")),
        (b"\x00\x00\x00\x1cftypmif1\x00\x00\x00\x00mif1heicmiaf", ("photo", "heic")),
        (b"\x00\x00\x00\x1cftypavif\x00\x00\x00\x00avifmif1miaf", ("photo", "avif")),
        (b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41", ("video", "mp4")),
        (b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  ", ("video", "mov")),
        (b"\x00\x00\x00\x18ftyp3gp4\x00\x00\x00\x00isom3gp4", ("video", "3gp")),
        (b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\x82\x84webm", ("video", "webm")),
        (b"\x1a\x45\xdf\xa3\xa3\x42\x86\x81\x01\x42\x82\x88matroska", ("video", "mkv")),
    ],
)
def test_detects_supported_types(header: bytes, expected: tuple[str, str]) -> None:
    found = sniff.detect(header)
    assert found is not None and (found.kind, found.ext) == expected


@pytest.mark.parametrize(
    "header",
    [b"<svg xmlns=", b"<!DOCTYPE html>", b"%PDF-1.7", b"PK\x03\x04", b"MZ\x90\x00", b"", b"\x00" * 32],
)
def test_rejects_everything_else(header: bytes) -> None:
    assert sniff.detect(header) is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("IMG-20230415-WA0012.jpg", datetime(2023, 4, 15, 12, 0, 0)),
        ("VID-20230415-WA0003.mp4", datetime(2023, 4, 15, 12, 0, 0)),
        ("WhatsApp Image 2023-04-15 at 18.30.12.jpeg", datetime(2023, 4, 15, 18, 30, 12)),
        ("WhatsApp Video 2023-04-15 at 9.05.01.mp4", datetime(2023, 4, 15, 9, 5, 1)),
        ("WhatsApp Imagen 2023-04-15 a las 18.30.12_abc.jpeg", datetime(2023, 4, 15, 18, 30, 12)),
        ("IMG_20230415_183012.jpg", datetime(2023, 4, 15, 18, 30, 12)),
        ("VID_20230415_183012.mp4", datetime(2023, 4, 15, 18, 30, 12)),
        ("Screenshot_20230415-183012.png", datetime(2023, 4, 15, 18, 30, 12)),
        ("Screenshot_2023-04-15-18-30-12-123_com.whatsapp.jpg", datetime(2023, 4, 15, 18, 30, 12)),
        ("20230415_183012.jpg", datetime(2023, 4, 15, 18, 30, 12)),
        ("20230415_183012(0).jpg", datetime(2023, 4, 15, 18, 30, 12)),
        ("Captura de pantalla 2023-04-15 a las 18.30.12.png", datetime(2023, 4, 15, 18, 30, 12)),
        ("Screen Shot 2023-04-15 at 6.30.12.png", datetime(2023, 4, 15, 6, 30, 12)),
        ("signal-2023-04-15-183012.jpg", datetime(2023, 4, 15, 18, 30, 12)),
        ("viaje/2023-04-15 playa.jpg", datetime(2023, 4, 15, 12, 0, 0)),
        ("scan_19991231.jpg", datetime(1999, 12, 31, 12, 0, 0)),
    ],
)
def test_filename_dates(name: str, expected: datetime) -> None:
    parsed = dates.parse_filename(name, today=date(2026, 1, 1))
    assert parsed is not None and parsed[0] == expected


def test_pixel_filenames_are_utc() -> None:
    parsed = dates.parse_filename("PXL_20230415_163012345.jpg", today=date(2026, 1, 1))
    assert parsed == (datetime(2023, 4, 15, 16, 30, 12), 0)
    found = dates.deduce(filename="PXL_20230715_163012345.jpg", uploaded_at=UPLOADED, default_tz=MADRID)
    assert found.local == datetime(2023, 7, 15, 18, 30, 12) and found.offset_minutes == 120


@pytest.mark.parametrize(
    "name",
    [
        "DSC01234.JPG",
        "foto.jpg",
        "IMG_1234.HEIC",
        "20231345_101010.jpg",
        "99999999.jpg",
        "IMG-20990101-WA0001.jpg",
        "21000101.jpg",
    ],
)
def test_filenames_without_valid_dates(name: str) -> None:
    assert dates.parse_filename(name, today=date(2026, 1, 1)) is None


def test_deduction_order() -> None:
    exif = dates.deduce(
        exif_original="2023:04:15 18:30:12",
        exif_offset="+09:00",
        filename="IMG-20200101-WA0001.jpg",
        uploaded_at=UPLOADED,
    )
    assert (exif.local, exif.offset_minutes, exif.source) == (datetime(2023, 4, 15, 18, 30, 12), 540, "exif")
    assert not exif.doubtful

    video = dates.deduce(
        video_created_utc=datetime(2023, 1, 10, 10, 0, tzinfo=UTC), uploaded_at=UPLOADED, default_tz=MADRID
    )
    assert (video.local, video.offset_minutes, video.source) == (datetime(2023, 1, 10, 11, 0), 60, "video")

    takeout = dates.deduce(
        exif_original="0000:00:00 00:00:00",
        takeout_timestamp=1681576212,
        filename="x.jpg",
        uploaded_at=UPLOADED,
        default_tz=MADRID,
    )
    assert takeout.source == "takeout" and takeout.local == datetime(2023, 4, 15, 18, 30, 12)

    name = dates.deduce(
        filename="IMG-20230415-WA0012.jpg", client_mtime_ms=1_600_000_000_000, uploaded_at=UPLOADED
    )
    assert name.source == "filename" and name.offset_minutes is None

    mtime = dates.deduce(
        filename="foto.jpg", client_mtime_ms=1_681_576_212_000, uploaded_at=UPLOADED, default_tz=MADRID
    )
    assert mtime.source == "mtime" and mtime.doubtful and mtime.local == datetime(2023, 4, 15, 18, 30, 12)

    future = dates.deduce(
        filename="foto.jpg", client_mtime_ms=4_000_000_000_000, uploaded_at=UPLOADED, default_tz=MADRID
    )
    assert future.source == "upload" and future.doubtful and future.local == datetime(2026, 11, 15, 13, 0)


@pytest.mark.parametrize(
    ("value", "minutes"),
    [("+09:00", 540), ("-03:30", -210), ("+0200", 120), ("Z", None), (None, None), ("+15:00", None)],
)
def test_offsets(value: object, minutes: int | None) -> None:
    assert dates.parse_offset(value) == minutes


def test_bad_exif_dates() -> None:
    assert dates.parse_exif_datetime("0000:00:00 00:00:00") is None
    assert dates.parse_exif_datetime("2023:13:01 00:00:00") is None
    assert dates.parse_exif_datetime(1234) is None
    assert dates.parse_exif_datetime("2023-04-15T18:30:12") == datetime(2023, 4, 15, 18, 30, 12)


@pytest.mark.parametrize(
    ("name", "camera", "exif", "expected"),
    [
        ("IMG-20230415-WA0012.jpg", None, False, "whatsapp"),
        ("WhatsApp Image 2023-04-15 at 18.30.12.jpeg", None, False, "whatsapp"),
        ("Screenshot_20230415-183012.png", None, False, "screenshot"),
        ("Captura de pantalla 2023-04-15 a las 18.30.12.png", None, False, "screenshot"),
        ("IMG_20230415_183012.jpg", None, False, "camera"),
        ("foto.jpg", "Google Pixel 8", True, "camera"),
        ("PXL_20230415_163012345.jpg", None, False, "camera"),
        ("meme.png", None, False, "other"),
    ],
)
def test_source(name: str, camera: str | None, exif: bool, expected: str) -> None:
    assert dates.deduce_source(name, camera=camera, has_exif_date=exif) == expected


def test_thumbhash_reference_shape() -> None:
    # Imagen 4x2: mitad izquierda roja, mitad derecha azul, opaca.
    pixels = bytearray()
    for _y in range(2):
        for x in range(4):
            pixels += bytes((255, 0, 0, 255) if x < 2 else (0, 0, 255, 255))
    value = rgba_to_thumbhash(4, 2, pixels)
    assert 5 < len(value) <= 25
    assert value[4] & 0x80  # apaisada
    assert not value[2] & 0x80  # sin transparencia
    # Determinista
    assert value == rgba_to_thumbhash(4, 2, pixels)
    with pytest.raises(ValueError):
        rgba_to_thumbhash(101, 1, bytes(101 * 4))
