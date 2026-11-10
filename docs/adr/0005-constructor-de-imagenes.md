# 0005 — Dockerfile compatible con el constructor clásico

- **Estado**: aceptada
- **Fecha**: 2026-11-07

## Contexto

El CI construye con BuildKit (`docker/build-push-action`), pero el mini PC no tiene `buildx` y
`docker build` usa el constructor clásico, que construye en orden todas las etapas anteriores a la pedida
y no admite opciones como `COPY --chmod`.

## Decisión

- El `Dockerfile` evita la sintaxis exclusiva de BuildKit.
- Las etapas van en este orden: `base` → `deps` → `dev` → `web` → `runtime`. Así `--target dev` (pruebas)
  no compila la web.
- La imagen `dev` (Python + dependencias de pruebas) es el entorno de pruebas en local y en el CI: misma
  versión de Python, de las dependencias y de `pg_dump`.

## Consecuencias

Si se instala `buildx` en el mini PC, todo sigue funcionando igual (y más rápido).
