# Políticas

Breves a propósito: Carrete lo usan unas pocas personas y lo mantiene una.

## Acceso
- Solo entra quien recibe una invitación. Nadie comparte cuenta.
- Segundo factor obligatorio para todos mientras Carrete esté abierto a internet.
- El administrador revisa cada trimestre la lista de personas y desactiva o borra a quien ya no deba entrar.
- Ante la pérdida de un móvil: cerrar sus sesiones desde Ajustes (o el administrador) y, si hace falta,
  restablecer el segundo factor con un enlace.

## Uso aceptable y clasificación
- Uso doméstico. Todo lo que hay en un espacio es privado de sus miembros.
- No se suben documentos ni nada que no sea una foto o un vídeo (la aplicación lo rechaza).

## Copias
- Copia automática en el mismo disco (base de datos cada hora, originales en minutos).
- Verificación semanal automática. Una restauración de prueba manual cada seis meses, siguiendo
  `docs/operacion.md`, además de la prueba automática del CI.
- Las fotos no se borran de los móviles mientras no exista una copia en otro soporte.

## Cambios
- Todo cambio pasa por el CI; `latest` solo se publica con todas las comprobaciones en verde.
- Las migraciones siguen el patrón expandir/contraer y van precedidas de un volcado.
- Volver atrás: fijar `CARRETE_IMAGE=…:<sha>`.

## Vulnerabilidades
- Dependabot propone actualizaciones cada semana; las de seguridad se aplican en cuanto pasan el CI.
- Una vulnerabilidad crítica en una dependencia expuesta (libvips, ffmpeg, FastAPI) sin parche: valorar
  cortar el Funnel (`tailscale funnel --https=10000 off`) hasta que lo haya.

## Secretos
- `POSTGRES_PASSWORD` y `CARRETE_SECRET_KEY` solo en `deploy/.env` (fuera de git) y en el gestor de
  contraseñas. Rotación: `docs/operacion.md`.
