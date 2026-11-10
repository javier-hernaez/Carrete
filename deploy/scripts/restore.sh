#!/bin/sh
# Restaura Carrete desde las copias. Uso:
#   deploy/scripts/restore.sh                       → el volcado horario más reciente
#   deploy/scripts/restore.sh carrete-2026….dump    → un volcado concreto (de copias/db/*/)
# Para app y worker, restaura la base de datos y los originales que falten, y vuelve a arrancar:
# el worker regenera solo las miniaturas y vistas previas que falten.
set -eu
cd "$(dirname "$0")/.."
. ./.env
DB_DIR="$CARRETE_ROOT/copias/db"
if [ $# -ge 1 ]; then
  FILE="$(find "$DB_DIR" -name "$1" | head -n 1)"
else
  FILE="$(ls -1 "$DB_DIR"/horarias/carrete-*.dump 2>/dev/null | sort | tail -n 1)"
fi
[ -n "${FILE:-}" ] && [ -f "$FILE" ] || { echo "No encuentro el volcado en $DB_DIR" >&2; exit 1; }
REL="${FILE#"$CARRETE_ROOT"/}"
echo "Se va a restaurar: $REL"
printf "Esto sustituye la base de datos actual. ¿Seguir? [s/N] "
read -r answer
[ "$answer" = "s" ] || [ "$answer" = "S" ] || { echo "Cancelado."; exit 1; }
docker compose stop app worker
docker compose up -d db
docker compose run --rm --no-deps backup carrete restore --dump "/storage/$REL"
docker compose up -d
echo "Hecho. Comprueba: docker compose ps   y   docker compose exec backup carrete verify"
