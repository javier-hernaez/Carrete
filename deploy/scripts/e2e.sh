#!/bin/sh
# Prueba de extremo a extremo: levanta un Carrete desechable en 127.0.0.1:8011 (proyecto «carrete-e2e»,
# carpetas temporales), ejecuta Playwright contra él y lo borra todo al terminar.
# Necesita la imagen ghcr.io/javier-hernaez/carrete:latest construida (make image).
set -eu
cd "$(dirname "$0")/.."
WORK="$(mktemp -d)"
TOKEN="e2e-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
cat > "$WORK/.env" <<ENV
CARRETE_IMAGE=${CARRETE_IMAGE:-ghcr.io/javier-hernaez/carrete:latest}
CARRETE_PUBLIC_URL=http://127.0.0.1:8011
CARRETE_PORT=8011
POSTGRES_PASSWORD=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
CARRETE_SECRET_KEY=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
CARRETE_SETUP_TOKEN=$TOKEN
# Carpeta temporal pequeña: la reserva de disco de producción (20 GB) no aplica aquí.
CARRETE_MIN_FREE_BYTES=50000000
CARRETE_ROOT=$WORK
CARRETE_ENV_FILE=$WORK/.env
CARRETE_UID=$(id -u)
CARRETE_GID=$(id -g)
ENV
mkdir -p "$WORK/datos" "$WORK/copias"
compose() { docker compose -p carrete-e2e --env-file "$WORK/.env" -f docker-compose.yml "$@"; }
cleanup() {
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$WORK" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
compose up -d --no-build --pull never
for _ in $(seq 1 60); do curl -fsS http://127.0.0.1:8011/readyz >/dev/null 2>&1 && break; sleep 2; done
docker run --rm --network host -u "$(id -u):$(id -g)" -e HOME=/tmp -e CI=1 \
  -e E2E_BASE_URL=http://127.0.0.1:8011 -e E2E_SETUP_TOKEN="$TOKEN" \
  -v "$PWD/../web:/web" -w /web mcr.microsoft.com/playwright:v1.49.0-noble npx playwright test "$@"

# Copias: volcado, espejo de originales y manifiestos de lo que ha subido la prueba; luego, integridad.
compose exec -T backup carrete backup
compose exec -T backup carrete verify
test -n "$(find "$WORK/copias/originals" -type f -name '*.jpg' 2>/dev/null)"
echo "Copias e integridad: correctas"
