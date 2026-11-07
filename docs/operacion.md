# Operación

Cómo instalar, actualizar, volver atrás y recuperar Carrete en el mini PC. Todas las órdenes se lanzan
desde `deploy/` y no necesitan `sudo`.

## Instalar

```sh
cd deploy
cp .env.example .env
```

Rellena en `.env`:

- `POSTGRES_PASSWORD` y `CARRETE_SECRET_KEY`: cada uno con `openssl rand -hex 32`. **Guárdalos en tu
  gestor de contraseñas**: sin `CARRETE_SECRET_KEY` no se pueden leer los secretos de segundo factor.
- `CARRETE_PUBLIC_URL`: mientras no se active el Funnel, `http://127.0.0.1:8010`.
- `CARRETE_DATA_DIR` y `CARRETE_BACKUP_DIR`: por defecto `/home/javier/carrete/datos` y `…/copias`.

Después:

```sh
./scripts/preparar-carpetas.sh   # crea las carpetas con tu usuario como dueño
docker compose up -d
docker compose ps                # app, worker, db y backup «healthy»
curl http://127.0.0.1:8010/readyz
```

Si la configuración no es válida, `app` no arranca y sus registros dicen qué variable corregir:
`docker compose logs app`. También: `docker compose run --rm app carrete check-config`.

## Actualizar

Automático: cada `push` a `main` que pasa el CI publica `ghcr.io/javier-hernaez/carrete:latest`, y el
Watchtower del equipo (`market_watchtower`) recrea `app` y `worker` en menos de un minuto. Al arrancar,
`app` hace un volcado de la base de datos y aplica las migraciones pendientes.

A mano: `docker compose pull && docker compose up -d`.

**Si el paquete de GHCR es privado**, Watchtower necesita credenciales para descargarlo:
comprobar cómo las tiene hoy para Atalaya (`docker inspect market_watchtower`, variables
`REPO_USER`/`REPO_PASS` o un `config.json` montado) y usar las mismas. No se modifica el contenedor
de Watchtower.

## Volver a una versión anterior

Cada publicación lleva también la etiqueta del commit. En `.env`:

```sh
CARRETE_IMAGE=ghcr.io/javier-hernaez/carrete:<sha-del-commit>
```

y `docker compose up -d`. Las migraciones siguen el patrón expandir/contraer, así que la versión anterior
funciona con el esquema nuevo. Watchtower no toca una imagen fijada por *sha*. Para volver a seguir las
publicaciones, deja `CARRETE_IMAGE` en `:latest`.

## Si una migración falla

`app` y `worker` no arrancan (código de salida 3) y el registro indica el volcado previo:

```sh
docker compose logs app | grep -i migra
ls "$CARRETE_DATA_DIR/db-premigracion/"
```

1. Vuelve a la versión anterior (apartado anterior): seguirá funcionando con el esquema de antes.
2. Abre una incidencia con el mensaje de error.
3. Si la base de datos hubiera quedado dañada, restaura el volcado previo (apartado siguiente).

## Restaurar la base de datos

Volcados: `CARRETE_BACKUP_DIR/db/{horarias,diarias,mensuales}/` y, antes de cada migración,
`CARRETE_DATA_DIR/db-premigracion/`.

```sh
docker compose stop app worker
docker compose exec -T db dropdb -U carrete carrete
docker compose exec -T db createdb -U carrete carrete
docker compose exec -T db pg_restore -U carrete -d carrete --no-owner < /ruta/al/volcado.dump
docker compose up -d app worker
```

Más adelante: `carrete restore` y la restauración de originales, con prueba automática en el CI.

## Copias de seguridad

El contenedor `backup` hace un volcado cada hora (`BACKUP_DB_INTERVAL_SECONDS`), lo verifica y conserva
48 horarios, 30 diarios y 12 mensuales. Está «unhealthy» si el último volcado correcto tiene más de dos
horas: `docker compose ps backup`, `docker compose logs backup`.

Volcado inmediato: `docker compose exec backup sh /backup.sh once`.

**Las copias están en el mismo disco que las fotos**: protegen de errores y borrados, no de
la rotura del disco, el robo o el incendio del mini PC.

## Exponer a internet

Solo con la revisión ASVS sin hallazgos altos y con confirmación expresa:

```sh
tailscale funnel --bg --https=10000 http://127.0.0.1:8010
```

y en `.env`: `CARRETE_PUBLIC_URL=https://javier-default-string.taila9c233.ts.net:10000`.

Cortar el acceso desde internet (p. ej. ante un incidente): `tailscale funnel --https=10000 off`.

Alternativa más segura: no activar Funnel y entrar solo por la red privada de Tailscale
(`tailscale serve --bg --https=10000 http://127.0.0.1:8010`), instalando Tailscale en cada móvil.

## Rotar secretos

- `POSTGRES_PASSWORD`: `docker compose exec db psql -U carrete -c "ALTER USER carrete PASSWORD '…'"`,
  cámbiala en `.env` y `docker compose up -d`.
- `CARRETE_SECRET_KEY`: invalida los secretos de segundo factor; habrá una orden para
  volver a cifrarlos con la clave nueva.

## Mover a otro equipo

1. `docker compose exec backup sh /backup.sh once` (volcado reciente).
2. `docker compose down`.
3. Copia `CARRETE_DATA_DIR`, `CARRETE_BACKUP_DIR` y `deploy/.env` al equipo nuevo (con `cp -a` o
   `rsync -aH`: **conserva los enlaces duros**).
4. En el equipo nuevo: `docker compose up -d db`, restaura el último volcado (apartado anterior) y
   `docker compose up -d`.

## Registros

JSON por la salida estándar, una línea por evento, con `request_id`:

```sh
docker compose logs -f app worker
docker compose logs app | grep '"level": "error"'
```

No contienen contraseñas, *tokens*, IP ni contenido de ficheros.
