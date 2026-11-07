# Carrete

Aplicación autoalojada para **reunir, ordenar y conservar** las fotos y vídeos de un grupo de personas
(pareja, familia), separadas en espacios. Corre en un mini PC con Docker y guarda los originales
intactos, con copia de seguridad, papelera y verificación de integridad.

- Arquitectura: [`docs/arquitectura.md`](docs/arquitectura.md) · Decisiones: [`docs/adr/`](docs/adr/)
- Operación (instalar, actualizar, volver atrás, restaurar): [`docs/operacion.md`](docs/operacion.md)
- Sistema de diseño: [`docs/diseno.md`](docs/diseno.md) · Seguridad: [`docs/seguridad/`](docs/seguridad/)
- Cambios: [`CHANGELOG.md`](CHANGELOG.md)

## Estado

En desarrollo. Ya están la estructura, la configuración validada, PostgreSQL + Alembic con
migraciones al arrancar, cola de tareas y `worker`, comprobaciones de salud, cabeceras de seguridad,
armazón de la web con su sistema de diseño, `docker-compose.yml` endurecido y CI completo.

## Puesta en marcha en 5 minutos

Necesitas Docker con Compose. Nada más: ni Python ni Node.

```sh
cd deploy
cp .env.example .env
# Rellena los secretos (cada uno con: openssl rand -hex 32) y revisa las carpetas
nano .env
./scripts/preparar-carpetas.sh
docker compose up -d            # o «docker compose up -d --build» para construir aquí la imagen
curl http://127.0.0.1:8010/readyz
```

La aplicación escucha solo en `127.0.0.1:8010`. Para abrirla a internet, ver
[`docs/operacion.md`](docs/operacion.md).

## Desarrollo

Todo corre en contenedores (`make help` para ver las órdenes):

```sh
make dev-image     # imagen de pruebas de Python (una vez, y al cambiar dependencias)
make web-install   # dependencias de la web
make check         # lo mismo que el CI: lint, tipos, pruebas con cobertura
make openapi       # regenera el cliente TypeScript tras cambiar la API
make dev           # web con recarga en http://127.0.0.1:5173 (con el backend de compose en marcha)
```

- Nueva migración: `docker run --rm -u $(id -u) -v $PWD:/src --network carrete-test
  -e CARRETE_DATABASE_URL=… carrete:dev alembic -c app/alembic.ini revision --autogenerate -m "…"`.
  Respeta el patrón expandir/contraer.
- Nunca uses fotos reales en pruebas ni en el repositorio.
- Commits convencionales en español: `feat: …`, `fix: …`, `docs: …`.

## Estructura

```
backend/   app/ (api, db, jobs, security, migrations)  tests/
web/       src/ (app, design-system, api, i18n)
android/   app Android
deploy/    Dockerfile  docker-compose.yml  .env.example  scripts/
docs/      adr/  seguridad/  arquitectura.md  diseno.md  operacion.md
```
