# 0001 — Pila tecnológica y estructura del repositorio

- **Estado**: aceptada
- **Fecha**: 2026-11-07

## Contexto

La pila sigue la línea de Atalaya para que haya un solo ecosistema que mantener.
Al montar la base del proyecto aparecieron incompatibilidades de versiones entre herramientas.

## Decisión

- Backend: Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2 (síncrono), Alembic, PostgreSQL 17.
- Web: React 18 + TypeScript + Vite, TanStack Query, React Router 7.
- **TypeScript 5.9 y ESLint 9**, no las últimas versiones mayores (TypeScript 6 y ESLint 10): ni
  `openapi-typescript` ni `eslint-plugin-jsx-a11y` las admiten todavía. Dependabot propondrá el salto
  cuando sea posible.
- Todas las dependencias con versión exacta: Python con *hash* (`requirements*.txt` generados con
  `uv pip compile --generate-hashes`) y la web con `package-lock.json`.
- Estructura: `backend/`, `web/`, `android/`, `deploy/`, `docs/`. El `Dockerfile` y
  `docker-compose.yml` viven en `deploy/`; la imagen se construye desde la raíz.
- El backend se ejecuta con `python -m app.cli` (orden `carrete` en la imagen); no se instala como
  paquete para no depender de una compilación con red dentro del `Dockerfile`.

## Consecuencias

- SQLAlchemy síncrono: las rutas de FastAPI corren en el grupo de hilos. Suficiente para 2–10 personas;
  las descargas grandes saldrán en flujo desde ficheros, sin pasar por la base de datos.
