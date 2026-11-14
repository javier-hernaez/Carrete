# Cambios

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versiones semánticas.

## [Sin publicar]

### Añadido — Mapa y lugares

- Nombre del lugar calculado en el servidor con GeoNames, sin servicios externos; búsqueda por lugar.
- Mapa del espacio con MapLibre, agrupado por zonas; al tocar una zona se abre la cuadrícula de ese
  lugar. OpenFreeMap por defecto (`CARRETE_MAP_STYLE_URL`, vacía para ocultarlo).
- «Lugar…» en la selección para poner o quitar la ubicación a mano, con deshacer.
- Sugerencias de álbum a partir de la bandeja de entrada (saltos de fecha y de lugar).
- Llaves de acceso (WebAuthn): entrar con huella, cara o PIN; alta y baja en Ajustes.
- Índice parcial para la línea temporal y prueba de rendimiento con 50 000 elementos.
- ADR 0010.

### Añadido — Funciones principales

- Acceso: asistente inicial, 2FA TOTP con códigos de recuperación, sesiones, invitaciones, roles por
  espacio, límites de intentos, auditoría y administración.
- Subir y ver: subida reanudable (tus), originales inmutables, miniaturas y vídeo, fechas de WhatsApp,
  línea temporal virtualizada, visor y filtros.
- Copias: agente con enlaces duros, volcados y manifiestos, integridad, restauración,
  papelera con purga, estado y avisos.
- Ordenar: revisar con teclado y gestos, selección múltiple, álbumes, favoritas, fechas, repetidas y
  actividad.
- Exportar e importar: ZIP por volúmenes con manifiesto, importación de ZIP y carpetas (WhatsApp, Takeout),
  biblioteca en disco, PWA y documentación de seguridad.
- App Android con «Compartir», cola en segundo plano y APK firmado.

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
