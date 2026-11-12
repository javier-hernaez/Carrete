# Declaración de aplicabilidad (Anexo A de ISO/IEC 27001:2022)

Carrete no busca la certificación (no tiene sentido para un uso doméstico), pero aplica los
controles del Anexo A que le corresponden. Los no listados no aplican: no hay organización, personal
contratado, proveedores con contrato ni instalaciones propias más allá de un equipo doméstico.

| Control | Aplica | Cómo se atiende | Dónde |
|---|---|---|---|
| A.5.1 Políticas | Sí | Políticas breves | `politicas.md` |
| A.5.9 Inventario de activos | Sí | Datos, contenedores, secretos, dependencias | `activos.md` |
| A.5.10 Uso aceptable | Sí | Uso doméstico, solo personas invitadas | `politicas.md` |
| A.5.12 Clasificación | Sí | Todo el contenido es privado del espacio | `politicas.md` |
| A.5.15–5.18 Control de acceso e identidades | Sí | Invitación, roles por espacio, 2FA, revocación | `backend/app/services/{auth,spaces}.py` |
| A.5.23 Servicios en la nube | Sí | Tailscale (túnel; no descifra) y GitHub (código e imagen; sin datos) | `activos.md` |
| A.5.24–5.28 Incidentes | Sí | Procedimiento | `incidentes.md` |
| A.5.29–5.30 Continuidad | Sí | Copias, restauración probada, RPO 1 h / RTO 2 h | `docs/operacion.md`; `test_restore_from_scratch` |
| A.5.33 Protección de registros | Sí | Auditoría de solo inserción, retención 2 años | migración `0001` |
| A.5.34 Privacidad | Sí | Datos mínimos, sin telemetría ni terceros, exportación completa, borrado de cuenta | `docs/seguridad/politicas.md` |
| A.7.10 Soportes de almacenamiento | Parcial | Cifrado en reposo opcional (LUKS) | Riesgo R12 aceptado |
| A.8.2–8.3 Accesos privilegiados | Sí | Administrador separado de los espacios; reautenticación | `backend/app/services/spaces.py` |
| A.8.5 Autenticación segura | Sí | Argon2id, TOTP, límites, sesiones | `asvs.md` V2–V3 |
| A.8.6 Capacidad | Sí | Panel de estado, avisos 80/90 %, reserva de disco | `backend/app/services/status.py` |
| A.8.7 Código malicioso | Sí | Tipo por contenido, `worker` aislado. Antivirus (ClamAV) valorado y descartado: ~1,5 GB de RAM en un equipo compartido para escanear fotos que nadie ejecuta | `amenazas.md` |
| A.8.8 Vulnerabilidades técnicas | Sí | `pip-audit`, `npm audit`, Trivy, Dependabot, Semgrep, bandit | `.github/workflows/ci.yml` |
| A.8.9 Configuración | Sí | Variables `CARRETE_*` validadas; `docker-compose.yml` versionado | `backend/app/config.py` |
| A.8.10 Borrado de información | Sí | Papelera, purga, retención de copias, borrado de cuentas | `services/trash.py`, `storage/purge.py` |
| A.8.12 Prevención de fugas | Sí | Aislamiento por espacio, medios privados, sin terceros | `test_spaces_are_isolated` |
| A.8.13 Copias de seguridad | Sí | Agente de copias, verificación, restauración probada | ADR 0008 |
| A.8.15–8.17 Registro, supervisión, reloj | Sí | Auditoría, registros JSON, avisos, UTC | `services/audit.py`, `observability.py` |
| A.8.20–8.22 Redes | Sí | Solo `127.0.0.1`, redes Docker internas, túnel | `deploy/docker-compose.yml` |
| A.8.24 Criptografía | Sí | TLS, Argon2id, AES-256-GCM (HKDF), SHA-256 | `backend/app/security/` |
| A.8.25–8.29 Desarrollo seguro y pruebas | Sí | CI, revisión ASVS, pruebas de seguridad | `asvs.md` |
| A.8.31 Separación de entornos | Sí | Datos sintéticos en pruebas, nunca fotos reales | `backend/tests/media_files.py` |
| A.8.32 Gestión de cambios | Sí | CI/CD, migraciones versionadas, vuelta atrás | `docs/operacion.md` |
