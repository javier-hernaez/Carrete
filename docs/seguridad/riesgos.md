# Análisis de riesgos

Escala: probabilidad (P) e impacto (I) de 1 a 3; riesgo = P × I. Revisar cada año o tras un cambio
importante (nuevo despliegue, copia externa, abrir a más personas).

| # | Riesgo | P | I | R | Tratamiento | Residual |
|---|---|---|---|---|---|---|
| R1 | Fuerza bruta o relleno de credenciales contra el acceso público | 3 | 3 | 9 | Sin registro abierto; Argon2id; 2FA obligatorio; límite de intentos por cuenta e IP con espera creciente; aviso ante ráfagas | Bajo |
| R2 | Robo de sesión (XSS, cookie) | 2 | 3 | 6 | CSP estricta sin `unsafe-inline`; React escapa la salida; cookie `__Host-` `HttpOnly` `Secure`; identificador opaco con hash en servidor; caducidad y revocación | Bajo |
| R3 | CSRF desde otra aplicación del mismo equipo (Atalaya, `pajiapp`) | 2 | 3 | 6 | `Origin` estricto con puerto + cabecera `X-Carrete-Request` en toda petición que modifica | Bajo |
| R4 | Una vulnerabilidad en otra aplicación del mismo nombre de equipo lee la cookie de Carrete | 1 | 3 | 3 | Las cookies no se separan por puerto: la cookie es `HttpOnly` (no la lee JavaScript de otra app), opaca y revocable | **Aceptado** |
| R5 | Fichero malicioso explota libvips, libheif o ffmpeg | 2 | 3 | 6 | Tipo real por contenido; límites de píxeles y duración; `worker` sin red, sin privilegios, solo lectura y con tiempo máximo; imagen actualizada (Trivy, Dependabot) | Medio-bajo |
| R6 | ZIP malicioso (bomba, rutas `../`) | 2 | 2 | 4 | Lectura por flujo sin rutas; límites de entradas, tamaño y proporción; bytes reales contados | Bajo |
| R7 | Un miembro accede a un espacio ajeno | 2 | 3 | 6 | Capa de acceso obligatoria; 404 a lo ajeno; pruebas de aislamiento en todos los puntos | Bajo |
| R8 | Pérdida de fotos por error de programación o humano | 2 | 3 | 6 | Originales inmutables; papelera 30 días; única vía de purga; copia con enlaces duros; verificación semanal | Bajo |
| R9 | Rotura del disco, robo o incendio del mini PC | 1 | 3 | 3 | Ninguna en esta versión (copias en el mismo disco); aviso permanente en el panel | **Aceptado** |
| R10 | Despliegue automático de una versión defectuosa | 2 | 2 | 4 | CI completo antes de `latest`; volcado antes de migrar; expandir/contraer; vuelta atrás por `:sha` | Bajo |
| R11 | Dependencia o imagen comprometida | 1 | 3 | 3 | Versiones fijadas con hash; `pip-audit`, `npm audit`, Trivy, SBOM; imágenes base oficiales | Bajo |
| R12 | Acceso físico al disco (fotos sin cifrar en reposo) | 1 | 3 | 3 | Opcional: LUKS (requiere `sudo`) | **Aceptado** |
| R13 | El administrador del servidor ve espacios ajenos en el disco | 1 | 2 | 2 | La interfaz no se lo permite; el acceso físico se documenta con transparencia | **Aceptado** |
| R14 | Abuso de recursos (subidas masivas que llenan el disco) | 2 | 2 | 4 | Solo personas invitadas; tamaño máximo por fichero; reserva de disco; avisos al 80 y 90 % | Bajo |
| R15 | Pérdida de la clave `CARRETE_SECRET_KEY` | 1 | 2 | 2 | Copia en el gestor de contraseñas; sin ella hay que volver a activar el 2FA de todos | Bajo |
