# Modelo de amenazas (STRIDE)

**Activos**: originales y su organización; credenciales y sesiones; secretos del servidor; copias.
**Actores**: atacante anónimo en internet; persona invitada curiosa o maliciosa; software de terceros
comprometido; el propio administrador cometiendo un error.

**Fronteras de confianza**

```
internet ──TLS──▶ tailscaled (Funnel) ──▶ 127.0.0.1:8010 ──▶ app ──▶ db
                                                          └──▶ cola ──▶ worker (sin red, ficheros no fiables)
                                                                          backup (sin red, ve las copias)
```

| Elemento | S (suplantación) | T (manipulación) | R (repudio) | I (divulgación) | D (denegación) | E (elevación) |
|---|---|---|---|---|---|---|
| Inicio de sesión | Contraseña + TOTP; códigos de un solo uso; sin enumeración de usuarios | — | Auditoría de éxitos y fallos con IP | Mensajes idénticos para usuario inexistente y contraseña mala | Límite de intentos sin bloqueo permanente | Asistente desactivado al existir una cuenta; código de arranque |
| Sesión (cookie) | Identificador aleatorio de 256 bits, hash en la base de datos | `HttpOnly`, `Secure`, `__Host-` | Lista de sesiones visible y revocable | CSP, sin terceros | — | Reautenticación para acciones sensibles |
| API | CSRF: `Origin` estricto + cabecera propia | Validación Pydantic; consultas parametrizadas | Auditoría de acciones relevantes | 404 a lo ajeno; documentación oculta en producción; errores sin detalles | Trozos ≤ 50 MB; límites de tamaño; paginación | Rol comprobado en cada petición, denegación por defecto |
| Subida (tus) | Sesión obligatoria; subida ligada a quien la empezó | SHA-256 recalculado; suma por trozo | Resumen por lote en la auditoría | Deduplicación solo dentro del espacio (no revela otros) | Espacio libre y reserva comprobados antes de aceptar bytes | Tipo real por contenido; SVG y HTML rechazados |
| Worker | — | Originales en solo lectura | Errores registrados por tarea | Sin red: no puede filtrar nada | Tiempo máximo, `nice`, límites de memoria y CPU | Sin privilegios, solo lectura, sin capacidades |
| Medios servidos | Sesión y pertenencia en cada fichero | — | — | `Cache-Control: private`; originales como adjunto; `nosniff` | Range para descargas grandes | — |
| Copias | — | Enlaces duros (borrar en `datos/` no afecta) y verificación semanal | Ejecuciones registradas | Carpeta no accesible para app y worker; sin secretos en la copia de configuración | Aviso si la copia se atrasa | Contenedor propio sin red |
| Administración | — | Auditoría de solo inserción (disparador) | Toda acción de administración auditada | El administrador no ve espacios ajenos | — | Reautenticación |
