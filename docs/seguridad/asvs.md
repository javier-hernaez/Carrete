# Revisión OWASP ASVS 4.0.3, nivel 2

Revisión del código del 12-11-2026. Estado: ✅ cumple · ⚠️ parcial o pendiente ·
— no aplica. Criterio para abrir a internet: **ningún hallazgo alto abierto** → se cumple; los ⚠️
son de prioridad media o baja y están anotados abajo.

| Capítulo | Requisitos clave | Estado | Evidencia |
|---|---|---|---|
| V1 Arquitectura | Modelo de amenazas, capas, componentes conocidos | ✅ | `amenazas.md`, ADR, SBOM |
| V2.1 Contraseñas | ≥ 12, sin composición ni caducidad, lista de comunes, hasta 256 caracteres, cambio con la actual | ✅ | `security/passwords.py`, `test_password_change_closes_other_sessions` |
| V2.2 Autenticación general | Límite de intentos sin bloqueo permanente; aviso al usuario y al administrador | ✅ | `security/ratelimit.py`, `test_rate_limit_without_permanent_lockout` |
| V2.4 Almacén de credenciales | Argon2id con sal; rehash si cambian los parámetros | ✅ | `passwords.py` |
| V2.5 Recuperación | Sin preguntas secretas; enlace de un solo uso del administrador; códigos de recuperación | ✅ | `services/invitations.py` |
| V2.7–2.8 OTP | TOTP RFC 6238, ventana ±1, sin reutilización, secretos cifrados | ✅ | `security/totp.py`, `test_login_with_totp_and_recovery_code` |
| V2.9 Criptografía de verificadores | — | — | No hay certificados de cliente |
| V3 Sesiones | Identificador aleatorio, hash en servidor, cookie `__Host-` `HttpOnly` `Secure` `SameSite`, caducidad, revocación, reautenticación | ✅ | `services/auth.py`, `test_session_cookie_attributes` |
| V4 Control de acceso | Denegación por defecto, en servidor, 404 a lo ajeno, matriz de roles | ✅ | `services/spaces.py`, `test_spaces_are_isolated`, `test_role_matrix` |
| V4.2.2 CSRF | Origin estricto + cabecera propia | ✅ | `security/csrf.py`, `test_csrf_protection` |
| V5 Validación y codificación | Pydantic, consultas parametrizadas, React escapa, nombres de fichero nunca como rutas | ✅ | `api/*`, `storage/naming.py` |
| V6 Criptografía | AES-256-GCM, HKDF por propósito, CSPRNG | ✅ | `security/crypto.py` |
| V7 Errores y registros | Sin datos sensibles en registros; auditoría de solo inserción; errores sin detalles internos | ✅ | `observability.py`, `test_audit_log_is_append_only`, `test_unhandled_errors_do_not_leak` |
| V8 Protección de datos | `Cache-Control: private`/`no-store`; sin terceros; borrado de cuenta; exportación completa | ✅ | `api/assets.py`, `api/admin.py` |
| V9 Comunicaciones | TLS en el mini PC (Funnel), HSTS | ⚠️ | Pendiente de comprobar al activar Funnel (ver abajo) |
| V10 Código malicioso | Dependencias fijadas con hash, análisis en CI | ✅ | `requirements*.txt`, CI |
| V11 Lógica de negocio | Límites de tamaño y espacio; acciones con deshacer; confirmación proporcional | ✅ | `services/batch.py`, `services/trash.py` |
| V12 Ficheros | Tipo por contenido, sin SVG/HTML, adjunto para originales, ZIP sin rutas y con límites | ✅ | `media/sniff.py`, `services/imports.py`, `test_import_zip_takeout_and_attacks` |
| V13 API | Esquema validado, `problem+json`, sin documentación en producción | ✅ | `test_docs_hidden_in_production` |
| V14 Configuración | Cabeceras (CSP, nosniff, frame-ancestors…), sin modo depuración, contenedores endurecidos, CI con Trivy | ✅ | `security/headers.py`, `docker-compose.yml` |

## Pendientes (ninguno alto)

1. **V9 / IP real tras Funnel** (medio). Al activar Funnel, comprobar con `docker compose logs app` que
   la IP que se registra en un acceso fallido es la del visitante y no la del propio equipo. Si fuera la
   del equipo, el límite por IP actuaría como límite global (el límite por cuenta sigue protegiendo).
2. **CI nunca ejecutado en GitHub** (medio). Las mismas comprobaciones pasan en local
   (`make check`, `deploy/scripts/e2e.sh`); gitleaks, Semgrep y Trivy se ejecutarán en el primer push.
3. **Cifrado en reposo** (bajo): riesgo R12 aceptado; LUKS opcional.
