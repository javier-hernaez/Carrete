# 0002 — Cola de tareas propia sobre PostgreSQL

- **Estado**: aceptada
- **Fecha**: 2026-11-07

## Contexto

Hace falta una cola sin Redis: Procrastinate o una tabla propia con `FOR UPDATE SKIP LOCKED`.

## Decisión

Tabla propia `jobs` (`app/jobs/queue.py`):

- Se toma la siguiente tarea con `SELECT … FOR UPDATE SKIP LOCKED` y se marca `running` en la misma
  transacción. Varios procesos pueden consumir sin pisarse (probado con 4 hilos en `tests/test_jobs.py`).
- Reintentos con espera creciente (30 s, 2 min, 8 min… hasta 1 h); al agotarlos queda `failed`, visible
  en el panel, nunca se borra sola.
- Las tareas «en curso» abandonadas (proceso muerto) vuelven a la cola pasados 30 minutos.
- Prioridad numérica (menor = antes) y ejecución diferida (`run_after`).

## Motivos

- Procrastinate trae su propio esquema, sus migraciones y un modelo asíncrono; para unos pocos tipos de
  tarea y un único `worker`, ~150 líneas propias son más fáciles de entender, probar y copiar.
- Todo el estado está en PostgreSQL: entra en las copias sin hacer nada más.

## Consecuencias

- Las tareas programadas (purga nocturna, verificación semanal) se implementarán encolando tareas con
  `run_after` desde el propio `worker`.
- Los manejadores tienen que ser idempotentes: una tarea puede ejecutarse dos veces si el proceso muere
  justo después de terminarla.
