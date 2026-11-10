#!/bin/sh
# OBSOLETO: las copias las hace «carrete backup-agent». Se puede borrar.
# Copia de seguridad de la base de datos (contenedor «backup»).
#
# Cada BACKUP_DB_INTERVAL_SECONDS: pg_dump comprimido → verificación con pg_restore --list → rotación.
# Retención: 48 horarias, 30 diarias y 12 mensuales. Las diarias y mensuales son enlaces duros a una
# horaria: no ocupan espacio adicional.
set -eu
umask 077  # copias legibles solo por su dueño

INTERVAL="${BACKUP_DB_INTERVAL_SECONDS:-3600}"
ROOT=/backups/db
KEEP_HOURLY=48
KEEP_DAILY=30
KEEP_MONTHLY=12

log() { printf '{"ts":"%s","service":"backup","msg":"%s"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1"; }

prune() { # prune <directorio> <cuántos conservar>
  ls -1 "$1"/carrete-*.dump 2>/dev/null | sort | head -n "-$2" | while read -r old; do rm -f "$old"; done
}

dump_once() {
  mkdir -p "$ROOT/horarias" "$ROOT/diarias" "$ROOT/mensuales"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  file="$ROOT/horarias/carrete-$stamp.dump"
  if ! pg_dump --format=custom --compress=6 --file="$file.partial"; then
    rm -f "$file.partial"; log "ERROR: pg_dump ha fallado"; return 1
  fi
  if ! pg_restore --list "$file.partial" >/dev/null; then
    rm -f "$file.partial"; log "ERROR: el volcado no se puede leer"; return 1
  fi
  mv "$file.partial" "$file"

  day="$(date -u +%Y%m%d)"; month="$(date -u +%Y%m)"
  ls "$ROOT/diarias"/carrete-"$day"T*.dump >/dev/null 2>&1 || ln "$file" "$ROOT/diarias/"
  ls "$ROOT/mensuales"/carrete-"$month"*.dump >/dev/null 2>&1 || ln "$file" "$ROOT/mensuales/"

  prune "$ROOT/horarias" "$KEEP_HOURLY"
  prune "$ROOT/diarias" "$KEEP_DAILY"
  prune "$ROOT/mensuales" "$KEEP_MONTHLY"
  touch /tmp/backup-ok
  log "Volcado correcto: $(basename "$file") ($(du -h "$file" | cut -f1))"
}

case "${1:-loop}" in
  once) dump_once ;;
  loop)
    log "Copias en marcha cada ${INTERVAL}s"
    trap 'log "Detenido"; exit 0' TERM INT
    while :; do
      dump_once || log "Se reintentará en el próximo ciclo"
      sleep "$INTERVAL" & wait $!
    done
    ;;
  *) echo "Uso: backup.sh [once|loop]" >&2; exit 2 ;;
esac
