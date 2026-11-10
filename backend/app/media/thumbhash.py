"""ThumbHash: marcador de ~25 bytes con los colores y la forma de cada foto.

Traducción del codificador de referencia (Evan Wallace, licencia MIT, https://evanw.github.io/thumbhash/).
La web lo descodifica para pintar algo parecido a la foto mientras carga la miniatura.
"""

from __future__ import annotations

import base64
import math


def _round(x: float) -> int:
    return math.floor(x + 0.5)  # Math.round de JavaScript


def rgba_to_thumbhash(w: int, h: int, rgba: bytes | bytearray) -> bytes:
    if w > 100 or h > 100:
        raise ValueError(f"{w}x{h} no cabe en 100x100")
    if len(rgba) != w * h * 4:
        raise ValueError("Tamaño de RGBA incorrecto")
    n = w * h
    avg_r = avg_g = avg_b = avg_a = 0.0
    for i in range(n):
        j = i * 4
        alpha = rgba[j + 3] / 255
        avg_r += alpha / 255 * rgba[j]
        avg_g += alpha / 255 * rgba[j + 1]
        avg_b += alpha / 255 * rgba[j + 2]
        avg_a += alpha
    if avg_a:
        avg_r /= avg_a
        avg_g /= avg_a
        avg_b /= avg_a

    has_alpha = avg_a < n
    l_limit = 5 if has_alpha else 7
    lx = max(1, _round(l_limit * w / max(w, h)))
    ly = max(1, _round(l_limit * h / max(w, h)))
    lum: list[float] = [0.0] * n
    p: list[float] = [0.0] * n
    q: list[float] = [0.0] * n
    a: list[float] = [0.0] * n
    for i in range(n):
        j = i * 4
        alpha = rgba[j + 3] / 255
        r = avg_r * (1 - alpha) + alpha / 255 * rgba[j]
        g = avg_g * (1 - alpha) + alpha / 255 * rgba[j + 1]
        b = avg_b * (1 - alpha) + alpha / 255 * rgba[j + 2]
        lum[i] = (r + g + b) / 3
        p[i] = (r + g) / 2 - b
        q[i] = r - g
        a[i] = alpha

    def encode_channel(channel: list[float], nx: int, ny: int) -> tuple[float, list[float], float]:
        dc = 0.0
        ac: list[float] = []
        scale = 0.0
        for cy in range(ny):
            cx = 0
            while cx * ny < nx * (ny - cy):
                fx = [math.cos(math.pi / w * cx * (x + 0.5)) for x in range(w)]
                f = 0.0
                for y in range(h):
                    fy = math.cos(math.pi / h * cy * (y + 0.5))
                    row = y * w
                    for x in range(w):
                        f += channel[x + row] * fx[x] * fy
                f /= n
                if cx or cy:
                    ac.append(f)
                    scale = max(scale, abs(f))
                else:
                    dc = f
                cx += 1
        if scale:
            ac = [0.5 + 0.5 / scale * v for v in ac]
        return dc, ac, scale

    l_dc, l_ac, l_scale = encode_channel(lum, max(3, lx), max(3, ly))
    p_dc, p_ac, p_scale = encode_channel(p, 3, 3)
    q_dc, q_ac, q_scale = encode_channel(q, 3, 3)
    if has_alpha:
        a_dc, a_ac, a_scale = encode_channel(a, 5, 5)

    is_landscape = w > h
    header24 = (
        _round(63 * l_dc)
        | (_round(31.5 + 31.5 * p_dc) << 6)
        | (_round(31.5 + 31.5 * q_dc) << 12)
        | (_round(31 * l_scale) << 18)
        | (int(has_alpha) << 23)
    )
    header16 = (
        (ly if is_landscape else lx)
        | (_round(63 * p_scale) << 3)
        | (_round(63 * q_scale) << 9)
        | (int(is_landscape) << 15)
    )
    out = [header24 & 255, (header24 >> 8) & 255, header24 >> 16, header16 & 255, header16 >> 8]
    ac_start = 6 if has_alpha else 5
    if has_alpha:
        out.append(_round(15 * a_dc) | (_round(15 * a_scale) << 4))
    channels = [l_ac, p_ac, q_ac, a_ac] if has_alpha else [l_ac, p_ac, q_ac]
    ac_index = 0
    for ac in channels:
        for f in ac:
            pos = ac_start + (ac_index >> 1)
            while len(out) <= pos:
                out.append(0)
            out[pos] |= _round(15 * f) << ((ac_index & 1) << 2)
            ac_index += 1
    return bytes(b & 255 for b in out)


def encode_b64(value: bytes) -> str:
    return base64.b64encode(value).decode()
