"""Tipo real de un fichero por su contenido, no por su extensión.

Solo se aceptan los formatos de la lista. SVG, HTML y cualquier otra cosa se rechazan.
"""

from __future__ import annotations

from dataclasses import dataclass

HEADER_BYTES = 64


@dataclass(frozen=True)
class FileType:
    kind: str  # "photo" | "video"
    mime: str
    ext: str


_HEIF_BRANDS = {b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1"}
_AVIF_BRANDS = {b"avif", b"avis"}
_QT_BRANDS = {b"qt  "}
_3GP_PREFIX = (b"3gp", b"3g2")
_MP4_BRANDS = {
    b"isom",
    b"iso2",
    b"iso3",
    b"iso4",
    b"iso5",
    b"iso6",
    b"mp41",
    b"mp42",
    b"avc1",
    b"M4V ",
    b"M4VP",
    b"dash",
    b"MSNV",
    b"NDAS",
    b"f4v ",
    b"mmp4",
    b"XAVC",
    b"MQT ",
}


def detect(header: bytes) -> FileType | None:
    if header.startswith(b"\xff\xd8\xff"):
        return FileType("photo", "image/jpeg", "jpg")
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return FileType("photo", "image/png", "png")
    if header[:6] in (b"GIF87a", b"GIF89a"):
        return FileType("photo", "image/gif", "gif")
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return FileType("photo", "image/webp", "webp")
    if header[:4] == b"\x1a\x45\xdf\xa3":  # EBML: Matroska o WebM
        if b"webm" in header[:HEADER_BYTES]:
            return FileType("video", "video/webm", "webm")
        return FileType("video", "video/x-matroska", "mkv")
    if header[4:8] == b"ftyp":
        major = header[8:12]
        # Las marcas compatibles van después de la versión menor, en bloques de 4 bytes.
        size = int.from_bytes(header[:4], "big")
        compatible = {header[i : i + 4] for i in range(16, min(size, len(header)) - 3, 4)}
        brands = {major} | compatible
        if major in _AVIF_BRANDS or (brands & _AVIF_BRANDS and not brands & _HEIF_BRANDS):
            return FileType("photo", "image/avif", "avif")
        if major in _HEIF_BRANDS or (brands & _HEIF_BRANDS and major not in _MP4_BRANDS | _QT_BRANDS):
            return FileType("photo", "image/heic", "heic")
        if major in _QT_BRANDS:
            return FileType("video", "video/quicktime", "mov")
        if major.startswith(_3GP_PREFIX):
            return FileType("video", "video/3gpp", "3gp")
        if major in _MP4_BRANDS or brands & _MP4_BRANDS:
            return FileType("video", "video/mp4", "mp4")
    # QuickTime antiguo sin «ftyp»: empieza por un átomo moov/mdat/wide/free.
    if header[4:8] in (b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot"):
        return FileType("video", "video/quicktime", "mov")
    return None
