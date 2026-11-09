"""Datos calculados de los derivados (ThumbHash, huella, vídeo), junto a ellos en disco.

Si el mismo original está en dos espacios, el segundo procesado no vuelve a generar nada.
"""

from __future__ import annotations

import json
from pathlib import Path


def write(out_dir: Path, thumbhash: str, dhash: int, has_video: bool) -> None:
    (out_dir / "info.json").write_text(
        json.dumps({"thumbhash": thumbhash, "dhash": dhash, "video": has_video})
    )


def read(out_dir: Path) -> tuple[str, int, bool]:
    data = json.loads((out_dir / "info.json").read_text())
    return str(data["thumbhash"]), int(data["dhash"]), bool(data["video"])
