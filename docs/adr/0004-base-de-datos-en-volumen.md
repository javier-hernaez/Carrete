# 0004 — PostgreSQL en un volumen de Docker; ficheros en carpetas del equipo

- **Estado**: aceptada
- **Fecha**: 2026-11-07

## Contexto

Los ficheros tienen que vivir en carpetas normales del equipo (montajes *bind*), no en
volúmenes de Docker, para que sobrevivan a `docker volume rm` y se vean desde el sistema.

## Decisión

- Fotos, derivados, subidas, exportaciones y biblioteca: carpeta del equipo (`CARRETE_DATA_DIR`).
- Copias: otra carpeta del equipo (`CARRETE_BACKUP_DIR`), solo accesible para el contenedor `backup`.
- Los ficheros internos de PostgreSQL: volumen con nombre (`carrete_pgdata`).

## Motivos

- Los ficheros de PostgreSQL no son legibles ni copiables «en caliente» como ficheros normales; lo que
  se copia y se restaura son los volcados, que sí están en la carpeta de copias.
- PostgreSQL exige un dueño y permisos concretos en su carpeta; con un montaje *bind* habría que
  resolver ese dueño a mano en el equipo.
- `--data-checksums` detecta corrupción de páginas.

## Consecuencias

- Mover Carrete a otro equipo = copiar las dos carpetas y `.env`, arrancar y restaurar el último volcado
  (`docs/operacion.md`). Es la misma operación que la prueba de restauración del CI.
- `docker volume rm carrete_pgdata` borra la base de datos viva: se recupera del último volcado (como
  mucho una hora de cambios de organización; ninguna foto).
