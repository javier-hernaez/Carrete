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
- `CARRETE_ROOT`: carpeta raíz, por defecto `/home/javier/carrete`, con `datos/` (fotos) y `copias/`
  (copias de seguridad) dentro. Van juntas para que la copia de originales use enlaces duros (ADR 0008).

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

## Copias de seguridad

El contenedor `backup` (orden `carrete backup-agent`) trabaja solo:

| Qué | Cuándo | Dónde (`CARRETE_ROOT/copias/`) |
|---|---|---|
| Originales nuevos (enlace duro o copia verificada) | cada 2 minutos | `originals/` |
| Volcado de la base de datos, verificado | cada hora | `db/horarias` (48), `db/diarias` (30), `db/mensuales` (12) |
| Manifiestos legibles por espacio | cada noche | `manifests/<espacio>/AAAA-MM-DD.jsonl` (30) |
| `docker-compose.yml` y nombres de las variables de `.env` | cada noche | `config/` |
| Verificación de integridad (SHA-256 de originales y copias) | cada semana | resultado en Administración |

Lo purgado de la papelera se conserva en `originals/` 30 días más (en total, 60 días para recuperar).

Órdenes útiles:

```sh
docker compose exec backup carrete backup          # copia inmediata de todo
docker compose exec backup carrete backup base     # solo la base de datos
docker compose exec backup carrete verify          # verificación de integridad ahora
docker compose ps backup                            # «unhealthy» si el último volcado tiene más de 2 h
```

**Las copias están en el mismo disco que las fotos**: protegen de errores y borrados, no de
la rotura del disco, el robo o el incendio del mini PC. No borres las fotos de los móviles hasta tener
una copia externa.

## Restaurar

```sh
deploy/scripts/restore.sh                        # el volcado horario más reciente
deploy/scripts/restore.sh carrete-20261110T1600Z.dump
```

Para `app` y `worker`, restaura la base de datos, devuelve a `datos/originals/` los originales que
falten (desde `copias/originals/`, comprobando su SHA-256) y vuelve a arrancar. El `worker` regenera las
miniaturas y vistas previas que falten. Después: `docker compose exec backup carrete verify`.

La misma secuencia (crear → copiar → destruir → restaurar → comprobar) se prueba en cada cambio:
`tests/test_conservation.py::test_restore_from_scratch`.

Si PostgreSQL no se pudiera restaurar, los manifiestos (`copias/manifests/`) dicen qué original
(`originals/ab/cd/<sha256>.<ext>`) es cada foto, con su fecha, álbumes y estado.

## Papelera y purga

Eliminar manda a la papelera; se recupera durante 30 días. Una tarea nocturna del `worker` purga lo que
lleve más de 30 días; el original solo se borra del disco si ningún otro elemento lo usa. «Vaciar
papelera» (solo el propietario, tecleando el nombre del espacio) purga en el momento. No existe ninguna
otra forma de borrar originales.

## Avisos

El `worker` revisa cada 15 minutos y avisa en Administración si: el disco pasa del 80 % o del 90 %, la
copia de la base de datos tiene más de 2 horas, hay originales sin copiar desde hace más de 15 minutos,
la verificación de integridad encuentra problemas, o hay ráfagas de accesos fallidos.

## Importar fotos antiguas

**Desde la web**: arrastra carpetas enteras o un `.zip` exportado de WhatsApp o de Google Fotos
(Takeout). El ZIP se importa en segundo plano con sus fechas y ubicaciones (`.json` de Takeout).

**Desde un disco del mini PC** (sin pasar por la red):

```sh
docker compose run --rm -v /media/disco/Fotos:/importar:ro app \
  carrete import /importar --space "Familia" --albums
```

`--albums` crea un álbum por cada carpeta de primer nivel; `--user lucia` atribuye la subida a otra
persona (por defecto, al propietario del espacio). Lo que ya estaba no se duplica.

## Exportar

- **Desde la web** (Más → Exportar): ZIP de un álbum, varios o el espacio entero (solo propietario), en
  partes de 4 GB que se descargan de forma reanudable. Incluye `carrete-manifest.json` y `.csv`.
  Caducan a los 7 días.
- **A una carpeta del servidor** (solo administrador): define `CARRETE_EXPORT_ROOTS` (p. ej.
  `/exportar`) y monta ese disco en `app` y `worker` (`- /media/usb:/exportar` en `volumes`).
- **Biblioteca en disco**: `CARRETE_ROOT/datos/library/<Espacio>/<Álbum>/…`, enlaces duros que se
  regeneran cada noche (o con «Regenerar ahora» en Administración, o `docker compose exec app carrete
  library`). Se puede abrir y copiar con cualquier explorador aunque Carrete esté parado.

## App Android

**Compilar** (dentro de Docker, sin instalar nada):

```sh
CARRETE_PUBLIC_URL=https://javier-default-string.taila9c233.ts.net:10000 android/build.sh
cp android/build/carrete.apk android/build/carrete-apk.json deploy/apk/
make image && cd deploy && docker compose up -d
```

La primera vez crea la **clave de firma** `android/keystore.jks` y su contraseña en
`android/.keystore-password`. **Guarda las dos con tus copias de seguridad y en el gestor de
contraseñas**: Android solo deja actualizar una app instalada si la nueva versión va firmada con la misma
clave. Para que el CI firme igual, súbelas a GitHub (Settings → Secrets → Actions):
`ANDROID_KEYSTORE_B64` (`base64 -w0 android/keystore.jks`) y `ANDROID_KEYSTORE_PASSWORD`; y la variable
`CARRETE_PUBLIC_URL`.

**Instalar**: Ajustes → App para el móvil → «Descargar la app», abrirla en el móvil y escanear el QR.

**Prueba guiada en un móvil real**:
1. Instalar, escanear el QR, entrar con usuario, contraseña y código.
2. En WhatsApp, elegir 50 fotos de un chat → Compartir → Carrete → espacio → Subir.
3. Apagar la pantalla a mitad de la subida; esperar a la notificación «Subida terminada».
4. Comprobar en la web que están las 50, una sola vez, con su fecha. Repetir el paso 2: «ya estaban».
5. Con «solo con wifi» (por defecto, para vídeos), compartir un vídeo con datos móviles: debe esperar.

## Mapa y lugares

- El nombre del lugar (ciudad y país) se calcula en el mini PC con datos de GeoNames incluidos en la
  imagen: ninguna coordenada sale de aquí.
- El mapa usa **OpenFreeMap** si `CARRETE_MAP_STYLE_URL` no está definida. Para otro proveedor, pon la
  dirección de su estilo; para quitar el mapa, déjala vacía (`CARRETE_MAP_STYLE_URL=`). Después,
  `docker compose up -d`. Si el proveedor sirve teselas o fuentes desde otro dominio, la CSP las
  bloqueará (ADR 0010).
- El lugar se calcula al procesar cada foto. Las que ya estaban antes de tener mapa lo reciben solas:
  el worker rellena 5 000 por hora.
- Las fotos de WhatsApp no traen ubicación, y Android la quita al compartir salvo con la app de Carrete
  (permiso `ACCESS_MEDIA_LOCATION`). Se pone a mano con «Lugar…» en la selección.

## Llaves de acceso

Ajustes → Llaves de acceso → «Añadir». Solo funcionan en la dirección de `CARRETE_PUBLIC_URL` (con
HTTPS, o `localhost`): una llave creada en `http://127.0.0.1:8010` no vale en el Funnel. Créalas cuando
esté activo. La contraseña y la 2FA siguen valiendo; quitar una llave pide volver a identificarse.

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

1. `docker compose exec backup carrete backup` (copia reciente).
2. `docker compose down`.
3. Copia `CARRETE_ROOT` entera y `deploy/.env` al equipo nuevo con `rsync -aH` (**-H conserva los
   enlaces duros**; sin él, las copias ocuparían lo mismo que las fotos).
4. En el equipo nuevo: `./scripts/preparar-carpetas.sh` (comprueba permisos) y
   `deploy/scripts/restore.sh`.

## Registros

JSON por la salida estándar, una línea por evento, con `request_id`:

```sh
docker compose logs -f app worker
docker compose logs app | grep '"level": "error"'
```

No contienen contraseñas, *tokens*, IP ni contenido de ficheros.
