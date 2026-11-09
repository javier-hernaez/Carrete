# 0007 — Servidor tus propio para la subida reanudable

- **Estado**: aceptada
- **Fecha**: 2026-11-09

## Contexto

La subida usa el protocolo tus 1.0 con las extensiones *creation*, *termination* y *checksum*. Hay
que decidir si se usa una biblioteca o una implementación propia.

## Decisión

Implementación propia en `backend/app/api/uploads.py` (~300 líneas), con `tus-js-client` en la web.

## Motivos

- Las bibliotecas de servidor tus para Python están poco mantenidas o atadas a otros marcos, y ninguna
  hace lo que Carrete necesita **antes** de aceptar bytes: comprobar el rol en el espacio, el tamaño
  máximo, el espacio libre (con reserva) y si el original ya está en el espacio.
- Lo que sigue a la subida (recalcular el SHA-256, validar el tipo por contenido, renombrado atómico a
  `originals/`, alta en la base de datos y encolado del procesado) es la parte crítica para la
  durabilidad y tiene que estar en nuestro código y en nuestras pruebas.
- El protocolo es pequeño: creación (`POST`), estado (`HEAD`), envío (`PATCH` con `Upload-Offset`) y
  cancelación (`DELETE`).

## Detalles

- Trozos de 16 MB en el cliente y nunca más de 50 MB por petición en el servidor.
- `Upload-Checksum: sha256 …` opcional por trozo; si no coincide, se descarta el trozo (código 460).
- El cliente identifica la subida por `espacio + SHA-256`: puede reanudarla tras cerrar la pestaña.
- Al terminar, el servidor responde con `Carrete-Asset-Id` y `Carrete-Duplicate`.
- Las subidas abandonadas se borran a las 48 h (tarea de mantenimiento del `worker`).

## Consecuencias

La app Android usa el mismo protocolo con un cliente propio sobre OkHttp.
