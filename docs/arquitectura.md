# Arquitectura

Resumen de cómo está construido Carrete. El porqué de cada decisión está en
los ADR de [`adr/`](adr/).

## Contenedores

```
 Internet ── Tailscale Funnel :10000 (tailscaled) ──────────▶ 127.0.0.1:8010
                                                                   │
  red «edge» (solo para publicar el puerto)                        │
  ┌────────────────────────────────────────────────────────────── app ─────┐
  │ red «internal» (internal: true → sin salida a internet)                 │
  │                                                                          │
  │   app      FastAPI + web estática. Migra al arrancar.     /data (rw)     │
  │   worker   cola de tareas; sin red exterior.              /data (rw)     │
  │   db       PostgreSQL 17 (volumen carrete_pgdata)                        │
  │   backup   copias: originales, volcados, manifiestos, integridad         │
  └──────────────────────────────────────────────────────────────────────────┘
```

- `app` y `worker` usan la misma imagen; cambia la orden (`carrete serve` / `carrete worker`).
- Todos corren sin privilegios (el usuario dueño de las carpetas del equipo), con sistema de ficheros de
  solo lectura, sin capacidades, `no-new-privileges` y límites de memoria y CPU.
- `db` necesita cinco capacidades para su script de arranque (cambiar de usuario y de dueño a sus
  ficheros); el resto se quitan.

## Backend (`backend/app`)

| Módulo | Qué hace |
|---|---|
| `config.py` | Configuración `CARRETE_*` validada al arrancar; errores que nombran la variable |
| `cli.py` | Orden `carrete`: `serve`, `worker`, `migrate`, `check-config`, `openapi` |
| `main.py` | Crea la aplicación FastAPI, la web estática con *fallback* a `index.html` |
| `migrate.py` | Migraciones con bloqueo consultivo y volcado previo ([ADR 0003](adr/0003-migraciones-al-arrancar.md)) |
| `db/` | Motor y sesiones de SQLAlchemy; modelos ORM |
| `migrations/` | Alembic. Una revisión por cambio de esquema |
| `jobs/` | Cola sobre PostgreSQL ([ADR 0002](adr/0002-cola-de-tareas-propia.md)), `worker`, manejadores |
| `api/` | Rutas: salud (`/healthz`, `/readyz`), `/api/v1/…`, errores `problem+json` |
| `security/` | Cabeceras de seguridad (CSP estricta, HSTS…) e identificador de petición |
| `observability.py` | Registros JSON por la salida estándar, sin datos personales |
| `ids.py` | UUIDv7 ([ADR 0006](adr/0006-uuidv7-propio.md)) |

Capas: rutas finas → servicios de dominio (`services/`,
`domain/`) → repositorios y almacenamiento (`storage/`, `media/`). La lógica de negocio no depende de
FastAPI ni del sistema de ficheros real.

### Rutas

| Ruta | Descripción |
|---|---|
| `GET /healthz` | El proceso responde (comprobación de salud de Docker) |
| `GET /readyz` | Base de datos accesible, esquema al día, carpeta de datos escribible. `503` si no |
| `GET /api/v1/info` | Nombre, versión y si el mapa está activo (público, sin datos) |
| `/api/docs` | Documentación interactiva, solo con `CARRETE_ENVIRONMENT=development` |
| `/assets/*` | Ficheros de la web con *hash*: caché de un año, inmutables |
| resto | `index.html` de la web (sin caché), o el fichero de la raíz si existe |

Las rutas `/api/*` que no existen devuelven `404` en `application/problem+json`, nunca HTML.

## Web (`web/src`)

| Carpeta | Qué contiene |
|---|---|
| `app/` | Armazón (navegación), rutas, páginas, configuración de TanStack Query |
| `design-system/` | *Tokens*, estilos base, componentes (`Icon`, `Logo`, `Button`, `EmptyState`) |
| `api/` | `client.ts` (peticiones, errores, cabecera anti-CSRF) y tipos generados de OpenAPI |
| `i18n/` | Textos de la interfaz, en español |
| `features/` | Funciones por pantalla |

El cliente TypeScript se genera de la especificación OpenAPI del backend (`make openapi`); el CI falla si
no está al día.

## Datos en disco

```
CARRETE_ROOT/
  datos/            ← app y worker (/data)          copias/          ← solo backup (/storage/copias)
    originals/        originales (0444)               originals/       espejo (enlaces duros)
    derivatives/      miniaturas, vistas previas      db/horarias, diarias, mensuales
    uploads/          subidas a medias (48 h)         manifests/<espacio>/AAAA-MM-DD.jsonl
    exports/          ZIP (7 días)                    config/          compose y nombres de variables
    library/          biblioteca en disco
    db-premigracion/  volcados antes de migrar
```

## Durabilidad

| Invariante | Cómo se garantiza | Prueba |
|---|---|---|
| Un original no cambia nunca | Renombrado atómico de un fichero verificado; 0444; nadie lo abre para escribir | `test_only_purge_deletes_originals` |
| Solo la purga borra originales | `app/storage/purge.py` es el único sitio | ídem |
| «Hecho» solo tras guardar, verificar y registrar | `_finalize` en `app/api/uploads.py` | `test_full_upload_and_processing` |
| Derivados, biblioteca y exportaciones se regeneran | Se reconstruyen desde originales y base de datos | `test_restore_from_scratch` |
| Las migraciones no tocan originales | Solo cambian el esquema; volcado previo | `test_migrations.py` |
