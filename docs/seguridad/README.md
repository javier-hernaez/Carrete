# Seguridad

Documentación del sistema de gestión de seguridad a pequeña escala. La revisión con OWASP ASVS 4.0
nivel 2 se hace **antes** de exponer la aplicación a internet.

| Documento | Contenido |
|---|---|
| `riesgos.md` | Análisis de riesgos y riesgos aceptados |
| `aplicabilidad.md` | Declaración de aplicabilidad (Anexo A de ISO/IEC 27001:2022) |
| `amenazas.md` | Modelo de amenazas STRIDE |
| `politicas.md` | Acceso, copias, cambios, vulnerabilidades |
| `activos.md` | Inventario: datos, contenedores, secretos, dependencias |
| `incidentes.md` | Detectar, contener, recuperar, aprender |
| `asvs.md` | Revisión ASVS nivel 2 |

## Controles implantados

| Control | Dónde |
|---|---|
| Puerto solo en `127.0.0.1`; `db`, `worker` y `backup` sin salida a internet | `deploy/docker-compose.yml` |
| Contenedores sin root, solo lectura, sin capacidades, `no-new-privileges`, límites | `deploy/docker-compose.yml` |
| Configuración validada al arrancar; secretos solo por entorno, `.env` fuera de git | `backend/app/config.py` |
| CSP estricta sin `unsafe-inline`, `frame-ancestors 'none'`, `nosniff`, HSTS, `Permissions-Policy` | `backend/app/security/headers.py` |
| Errores sin detalles internos (`problem+json`); documentación de la API oculta en producción | `backend/app/api/errors.py`, `main.py` |
| Registros sin datos personales ni secretos | `backend/app/observability.py` |
| Auditoría de solo inserción (disparador en la base de datos) | migración `0001` |
| Identificadores no enumerables (UUIDv7) | `backend/app/ids.py` |
| Dependencias fijadas con *hash*; `pip-audit`, `npm audit`, Dependabot | `backend/requirements*.txt`, CI |
| Análisis estático (ruff con reglas `S`, bandit, Semgrep), secretos (gitleaks) | CI, `pre-commit` |
| Imagen analizada con Trivy antes de publicar; SBOM | CI |
| Cabecera anti-CSRF en todas las peticiones de la web | `web/src/api/client.ts` |

## Riesgos ya identificados

- **Nombre de equipo compartido** con Atalaya y `pajiapp` en Tailscale Funnel: las cookies no
  se separan por puerto y `SameSite` no protege entre ellas. Mitigación obligatoria:
  comprobación estricta de `Origin` con puerto, cabecera personalizada, cookie `__Host-carrete` con
  identificador opaco. Riesgo residual aceptado: un fallo en otra de esas aplicaciones podría afectar
  a la sesión de Carrete.
- **Copias en el mismo disco**: no protegen de la rotura del disco ni del robo del equipo.
- **Sin cifrado en reposo** de los originales: mitigación opcional con LUKS (requiere `sudo`).
