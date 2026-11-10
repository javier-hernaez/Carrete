# 0006 — Identificadores UUIDv7 propios

- **Estado**: aceptada
- **Fecha**: 2026-11-07

## Contexto

Los identificadores son UUIDv7 (no enumerables, ordenables por tiempo). Python 3.13 no incluye
`uuid.uuid7()` (llega en 3.14).

## Decisión

Implementación propia en `app/ids.py` según RFC 9562: 48 bits de milisegundos, 12 bits de contador
monótono y 62 bits aleatorios de `os.urandom`. Probada en `tests/test_ids.py`.

## Consecuencias

Al pasar a Python 3.14 se podrá sustituir por `uuid.uuid7()` sin cambiar los datos guardados.
