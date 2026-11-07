#!/bin/sh
# Órdenes de administración dentro del contenedor: docker compose exec app carrete <orden>
exec python -m app.cli "$@"
