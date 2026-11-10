#!/bin/sh
# Crea las carpetas de datos y de copias con el dueño correcto ANTES del primer arranque.
# Si no existen, Docker las crea como root y los contenedores (que no corren como root) no podrían
# escribir en ellas. No necesita sudo si las rutas están dentro de tu carpeta personal.
set -eu
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Falta deploy/.env: cópialo de .env.example y rellénalo primero." >&2
  exit 1
fi
# shellcheck disable=SC1091
. ./.env

: "${CARRETE_ROOT:?Define CARRETE_ROOT en .env}"
CARRETE_DATA_DIR="$CARRETE_ROOT/datos"
CARRETE_BACKUP_DIR="$CARRETE_ROOT/copias"

for dir in "$CARRETE_ROOT" "$CARRETE_DATA_DIR" "$CARRETE_BACKUP_DIR"; do
  mkdir -p "$dir"
  chmod 700 "$dir"
  echo "Lista: $dir ($(stat -c '%U:%G' "$dir"))"
done

data_dev="$(stat -c %d "$CARRETE_DATA_DIR")"
backup_dev="$(stat -c %d "$CARRETE_BACKUP_DIR")"
if [ "$data_dev" = "$backup_dev" ]; then
  echo "Aviso: las copias están en el mismo disco que las fotos."
  echo "       Protegen de errores y borrados, no de la rotura del disco."
fi
