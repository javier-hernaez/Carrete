# Cambios

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versiones semánticas.

## [Sin publicar]

### Añadido — Base del proyecto

- Estructura del repositorio, `Makefile` con todas las órdenes de desarrollo en Docker, `pre-commit`.
- Backend: configuración `CARRETE_*` validada al arrancar, PostgreSQL 17 + Alembic con migraciones al
  arrancar (bloqueo consultivo y volcado previo), cola de tareas sobre PostgreSQL y `worker`,
  `/healthz` y `/readyz`, errores `problem+json`, cabeceras de seguridad, registros JSON, orden
  `carrete`.
- Primera migración: cola de tareas y registro de auditoría de solo inserción.
- Web: armazón (barra inferior en móvil, lateral en escritorio), sistema de diseño con tema claro y
  oscuro, estados vacíos, cliente de la API con tipos generados de OpenAPI.
- Despliegue: `Dockerfile` multi-etapa, `docker-compose.yml` endurecido con redes separadas, copias
  horarias de la base de datos.
- CI: lint, tipos, pruebas con cobertura mínima, auditoría de dependencias, gitleaks, Semgrep, Trivy,
  SBOM y publicación en GHCR solo si todo pasa.
- Documentación: arquitectura, diseño, operación, seguridad y ADR 0001–0006.
