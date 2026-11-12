# Respuesta ante incidentes

## 1. Detectar
Señales: avisos de Administración (ráfagas de accesos fallidos, uso de códigos de recuperación,
integridad, copia atrasada), registros (`docker compose logs app worker`), una persona que avisa.

## 2. Contener (minutos)
- **Sospecha de acceso indebido**: cortar internet con `tailscale funnel --https=10000 off`.
  La aplicación sigue funcionando en la red privada de Tailscale.
- **Cuenta comprometida**: Administración → Personas → «Cerrar sus sesiones» y «Restablecer contraseña
  y 2FA»; o desactivar la cuenta.
- **Todas las sesiones**: rotar `CARRETE_SECRET_KEY` no basta (las sesiones no dependen de ella);
  `docker compose exec db psql -U carrete -c "UPDATE sessions SET revoked_at = now()"`.
- **Versión defectuosa**: fijar la anterior (`CARRETE_IMAGE=…:<sha>`) y `docker compose up -d`.

## 3. Evaluar
- Auditoría: Administración → Registro de auditoría (filtrar por `auth.`, `export.`, `user.`).
- ¿Hubo exportaciones o descargas? `export.created` en la auditoría.
- ¿Integridad de los originales? `docker compose exec backup carrete verify`.

## 4. Recuperar
- Restaurar si hace falta (`deploy/scripts/restore.sh`).
- Rotar secretos afectados (`docs/operacion.md`).
- Volver a abrir el Funnel solo cuando la causa esté corregida y desplegada.

## 5. Aprender
Anotar en `docs/seguridad/registro-incidentes.md`: fecha, qué pasó, cómo se detectó, qué se hizo y qué
se cambia para que no se repita.
