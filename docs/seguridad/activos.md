# Inventario de activos

| Activo | Dónde | Sensibilidad | Copia |
|---|---|---|---|
| Originales (fotos y vídeos) | `CARRETE_ROOT/datos/originals` | Alta (privada) | `copias/originals` (enlaces duros) |
| Base de datos (cuentas, organización, auditoría) | volumen `carrete_pgdata` | Alta | `copias/db` cada hora |
| Derivados, biblioteca, exportaciones | `datos/derivatives`, `datos/library`, `datos/exports` | Alta, regenerables | No (se regeneran) |
| `POSTGRES_PASSWORD`, `CARRETE_SECRET_KEY` | `deploy/.env` | Crítica | Gestor de contraseñas |
| Imagen de la aplicación | `ghcr.io/javier-hernaez/carrete` | Pública o privada según el repositorio | GHCR (`:latest`, `:<sha>`) |
| Código | GitHub `javier-hernaez/carrete` | Baja | GitHub |
| Clave de firma del APK | Secretos de GitHub Actions + copia del usuario | Crítica | Copia del usuario |

## Contenedores

| Contenedor | Imagen | Red | Datos |
|---|---|---|---|
| `app` | Carrete | interna + publicación en `127.0.0.1:8010` | `datos/` |
| `worker` | Carrete | solo interna | `datos/` |
| `backup` | Carrete | solo interna | `CARRETE_ROOT` (datos y copias) |
| `db` | `postgres:17-alpine` | solo interna | `carrete_pgdata` |

## Servicios externos

| Servicio | Para qué | Qué ve | Cómo prescindir |
|---|---|---|---|
| Tailscale (Funnel) | Dirección pública con TLS | Metadatos de conexión; **no** el contenido (el TLS termina en el mini PC) | Entrar solo por la red privada de Tailscale, o cambiar de túnel (`CARRETE_PUBLIC_URL`) |
| GitHub (repositorio, Actions, GHCR) | Código, CI e imagen | El código; nunca datos ni secretos de producción | Construir la imagen en el equipo (`make image`) |
| Proveedor de teselas del mapa (opcional) | Fondo del mapa | Las zonas del mapa que se miran; nunca fotos ni coordenadas exactas | Dejar `CARRETE_MAP_STYLE_URL` vacío |

## Dependencias
Fijadas con hash en `backend/requirements*.txt` y en `web/package-lock.json`; SBOM (SPDX) en cada
publicación del CI.
