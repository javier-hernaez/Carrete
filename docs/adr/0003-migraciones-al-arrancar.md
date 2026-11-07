# 0003 — Migraciones al arrancar, con bloqueo y volcado previo

- **Estado**: aceptada
- **Fecha**: 2026-11-07

## Contexto

El despliegue es automático (Watchtower). Las migraciones tienen que aplicarse una sola vez,
precedidas de un volcado, y que la aplicación no arranque si una migración falla.

## Decisión

`app/migrate.py`, invocado por `carrete serve` y `carrete worker` antes de empezar:

1. Toma un bloqueo consultivo de PostgreSQL (`pg_advisory_lock`). `app` y `worker` arrancan a la vez;
   el segundo espera y, al entrar, ve que ya no queda nada pendiente.
2. Si hay migraciones pendientes **y** la base de datos ya tenía esquema, hace `pg_dump` y lo verifica
   con `pg_restore --list`. Si el volcado falla, no migra.
3. Aplica cada migración en su propia transacción. Si alguna falla, el proceso termina con código 3 y un
   mensaje que señala el volcado previo; Docker lo reintentará, pero nunca sirve con el esquema a medias.

Los volcados previos se guardan en `CARRETE_DATA_DIR/db-premigracion/` (se conservan los 10 últimos).

## Alternativa descartada

Guardarlos en `CARRETE_BACKUP_DIR`: `app` y `worker` no deben tener acceso a la carpeta de
copias (así un fallo de la aplicación no puede dañarlas). Las copias horarias del contenedor `backup`
cubren igualmente la base de datos.

## Consecuencias

- La imagen incluye `postgresql-client-17` (`pg_dump` de la misma versión que el servidor).
- Las migraciones siguen el patrón expandir/contraer: la versión anterior de la aplicación debe
  funcionar con el esquema nuevo, porque la imagen puede volver atrás pero el esquema no.
- El registro de auditoría es de solo inserción por un disparador; su purga a los 2 años exige
  `SET LOCAL carrete.audit_purge = 'on'` dentro de la tarea que la haga.
