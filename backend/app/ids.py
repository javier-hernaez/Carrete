"""Identificadores UUIDv7 (RFC 9562).

Ordenables por tiempo (buenos para índices) y no enumerables: los 74 bits aleatorios impiden adivinar
identificadores ajenos. Python 3.13 aún no trae ``uuid.uuid7``; esta implementación es monótona dentro
del mismo proceso aunque se generen varios en el mismo milisegundo.
"""

from __future__ import annotations

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms = 0
_last_counter = 0

_COUNTER_BITS = 12
_COUNTER_MAX = (1 << _COUNTER_BITS) - 1


def uuid7() -> uuid.UUID:
    global _last_ms, _last_counter  # noqa: PLW0603  # estado del generador, protegido por el cerrojo
    with _lock:
        now_ms = time.time_ns() // 1_000_000
        if now_ms > _last_ms:
            _last_ms = now_ms
            # Contador inicial aleatorio en la mitad baja para dejar margen de incremento.
            _last_counter = int.from_bytes(os.urandom(2)) & (_COUNTER_MAX >> 1)
        else:
            _last_counter += 1
            if _last_counter > _COUNTER_MAX:
                # Se agotó el contador en este milisegundo: se avanza el reloj lógico.
                _last_ms += 1
                _last_counter = 0
        ms, counter = _last_ms, _last_counter

    rand_b = int.from_bytes(os.urandom(8)) & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # versión 7
    value |= counter << 64  # rand_a: contador monótono
    value |= 0b10 << 62  # variante RFC 9562
    value |= rand_b
    return uuid.UUID(int=value)


def uuid7_time_ms(value: uuid.UUID) -> int:
    """Marca de tiempo (ms desde 1970) codificada en un UUIDv7."""
    return value.int >> 80
