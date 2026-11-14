"""Nombres y carpetas de las exportaciones y de la biblioteca en disco.

Los nombres que pone la gente (espacios, álbumes, ficheros) se limpian para que sean válidos en
cualquier sistema (Windows incluido) y nunca puedan salirse de su carpeta.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import PurePosixPath

NO_ALBUM = "Sin álbum"
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
MAX_COMPONENT = 120


def safe_component(name: str, fallback: str = "sin-nombre") -> str:
    name = unicodedata.normalize("NFC", name)
    name = _FORBIDDEN.sub("_", name).strip().strip(".")
    name = " ".join(name.split())
    if not name or name in {".", ".."}:
        name = fallback
    if name.split(".")[0].upper() in _RESERVED:
        name = f"_{name}"
    if len(name) > MAX_COMPONENT:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 8:
            name = stem[: MAX_COMPONENT - len(ext) - 1] + "." + ext
        else:
            name = name[:MAX_COMPONENT]
    return name


def file_name(original: str, taken_at: datetime, ext: str, *, normalized: bool) -> str:
    """Nombre del fichero: el original, o «AAAA-MM-DD_HHMMSS_nombre.ext» (ordena bien en cualquier sitio)."""
    base = safe_component(PurePosixPath(original.replace("\\", "/")).name)
    stem = base.rsplit(".", 1)[0] if "." in base else base
    if not normalized:
        return base if "." in base else f"{base}.{ext}"
    return safe_component(f"{taken_at:%Y-%m-%d_%H%M%S}_{stem}.{ext}")


def folders_for(structure: str, taken_at: datetime, albums: list[str]) -> list[str]:
    """Carpetas donde va un elemento. Por álbum: una por álbum, o «Sin álbum/AAAA/MM»."""
    by_date = f"{taken_at:%Y}/{taken_at:%m}"
    if structure == "flat":
        return [""]
    if structure == "date":
        return [by_date]
    if albums:
        return [safe_component(a) for a in albums]
    return [f"{NO_ALBUM}/{by_date}"]


class UniqueNames:
    """Evita choques de nombres dentro de una misma carpeta: «foto.jpg», «foto (2).jpg»…"""

    def __init__(self) -> None:
        self.used: set[str] = set()

    def claim(self, folder: str, name: str) -> str:
        candidate = f"{folder}/{name}" if folder else name
        counter = 2
        stem, dot, ext = name.rpartition(".")
        while candidate.lower() in self.used:
            alt = f"{stem} ({counter}).{ext}" if dot else f"{name} ({counter})"
            candidate = f"{folder}/{alt}" if folder else alt
            counter += 1
        self.used.add(candidate.lower())
        return candidate
