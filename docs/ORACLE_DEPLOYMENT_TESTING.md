# Verificación Oracle y evaluación de punta a punta

Fecha: 2026-10-15. Ningún resultado local se presenta como prueba de OCI.
La evidencia ejecutable de esta revisión está en
`enterprise-evidence/2026-10-15-continuous/oracle-*` y `oracle-evidence/2026-10-15/`.
Los JSON registran comando, directorio, código de salida y duración.

## Resultados locales

| Comprobación | Resultado actual | Evidencia / alcance |
| --- | --- | --- |
| Git local/remoto | HEAD 2ad91d7 coincidente, limpio al inicio | Consulta HTTPS; SSH falló por permisos de configuración local. |
| Backend completo | 367 aprobadas en la regresión final | oracle-backend-reviewed; PG 18.6, Python 3.14.7. |
| Cobertura | 92 %, umbral 85 % mantenido | oracle-coverage-reviewed; 5.370 sentencias, 415 sin ejecutar. |
| MFA específico | 14 incluidas en regresión final; browser real aprobado | oracle-mfa-tests / oracle-mfa-browser; ampliadas carreras en regresión final. |
| Ruff | Aprobado tras ordenar imports | oracle-final-lint; fallo inicial conservado. |
| TypeScript | Aprobado | oracle-frontend-typecheck. |
| ESLint | Aprobado | oracle-final-frontend-lint. |
| Contrato ESLint | 2 pruebas aprobadas | oracle-lint-contract; conserva detección de reglas oficiales Next. |
| Build producción | Aprobado, Webpack | oracle-build-retry. Primer intento sandbox falló al leer showConfig; conservado. |
| npm audit completo | 0 vulnerabilidades | oracle-npm-audit, instalación limpia; no se omiten devDependencies. |
| pip-audit con lock | 0 vulnerabilidades conocidas | oracle-pip-audit. |
| OpenAPI | Aprobado | oracle-validation, salida 0. |
| Browser suite actual | 53 aprobados / 18 archivos | oracle-browser-all, salida 0, 565,75 s; browser-summary.json. |
| Compose real 5.6.0 config | Aprobado, solo proxy publica puertos | compose-validation.json; sin Docker Engine/contendores. |
| ARM64 imágenes | 5 manifiestos linux/arm64 encontrados | arm64-manifests.json; no ejecutados. |
| ARM64 Python | 34 ruedas compatibles descargadas | python-arm64-wheels.json; sin ejecución ARM. |
| ARM64 npm | npm ci ARM64 terminó con 0 alertas | Instalación aislada --ignore-scripts; falta build/ejecución. |
| Restic recuperación | Aprobada e igual antes/después | restic-recovery.json; repositorio local cifrado, read-data completo, PG18.6. |
| Checks deploy estrictos | Fallan con W005/W021 de HSTS | oracle-deploy-check; política explícita, sin ocultar warnings. |

El npm ci informa además deprecación de ESLint 9.39.5. No es la vulnerabilidad de
braces ni una falla de lint. No forzar un major incompatible con sus plugins para
ocultar el mensaje; revisar actualización compatible cuando el ecosistema lo soporte.

## Verificación obligatoria en VM y dominio reales

Pendientes: construir linux/arm64, PostgreSQL 17 y Redis 8 reales, Compose completo,
worker/scheduler, checks/migraciones, SMTP, reinicios, permisos/red y backup externo.
Registrar CPU/RAM/disco y digests; la propuesta de recursos no es una medición.

Desde el dominio aprobado, Playwright debe usar cuentas sintéticas independientes:
registro según política demo, login/logout, MFA, recuperación con email autorizado,
selección de empresa, roles/desactivación, configuración/equipo, clientes/catálogo,
borrador/emisión, impuestos/totales, pagos parciales/totales/reversiones, cartera,
auditoría, analytics/filtros, ocho reportes CSV/XLSX/PDF, notificaciones/automatización,
proveedores, gastos/adjuntos/pagos y compras/recepciones/stock. Recargar y comprobar
persistencia, respuestas backend, bloqueo de escrituras y cruce de identificadores
entre al menos dos empresas. No enviar correo a terceros ni usar datos comerciales.

Repetir desktop, tablet y mobile; teclado/foco, modales, cargas/vacíos/errores,
Axe y revisión manual de contraste, reduced-motion, consola y respuestas 5xx.
Las capturas nunca incluyen contraseñas, semillas MFA, recuperación o tokens.

Comprobar /, /admin/, /static/ con un archivo real, /health/ y /ready/.
`/api/` sin recurso no tiene índice público y puede devolver 404; `/api/docs/` y
`/api/schema/` deben estar cerrados en producción. Un 404 esperado no equivale a
backend caído. Probar rutas reales autenticadas para demostrar funcionamiento.

HTTPS: HTTP→HTTPS, cadena/certificado y renovación persistente, cookies Secure /
HttpOnly / SameSite, CSRF, sin contenido mixto y cabeceras observadas desde fuera.
Probar que 5432/6379/8000/3000 no sean accesibles y SSH solo desde CIDR aprobado.
Pruebas de carga acotadas inicialmente a 2–5 sesiones sintéticas, detener ante
5xx, RAM/disco alto o tiempos excesivos; no ejecutar ataques sobre terceros.

Resiliencia: reiniciar un contenedor a la vez, worker caído sin perder jobs,
lease/reintentos sin duplicados, reinicio VM con datos persistentes, backup externo
y restauración en base NUEVA PostgreSQL 17. No apagar servicios sin ventana acordada.
No publicar métricas hasta medirlas y guardar comandos/duración/error/entorno.

## Límites de validación adicionales

`systemd-analyze verify` no pudo resolver Requires=docker.service en este equipo,
que no tiene Docker instalado. Se conserva como bloqueado por entorno; volver
a ejecutarlo en Ubuntu después de instalar Engine. No se habilitó el timer.
La sintaxis Bash pasó `bash -n`. `makemigrations --check --dry-run` no encontró
cambios; su repetición con acceso al PostgreSQL aislado pasó sin el aviso inicial
del sandbox. `migrate --check` confirmó la base E2E al día.

La instalación ARM64 de Node incluyó SWC 16.4.0, Tailwind Oxide 4.3.3 y
Lightning CSS 1.32.0; `file` los identificó como ELF aarch64. Es evidencia de
arquitectura/disponibilidad y no ejecución. Ver node-arm64.json.

## Revisión posterior del artefacto

El build final `oracle-build-session-refresh` aprobó tras actualizar automáticamente
la tabla de sesiones al activar/cambiar MFA. `oracle-mfa-reviewed-browser` repitió
los dos recorridos afectados (MFA y seguridad con dos navegadores): ambos pasaron,
incluido foco en el código y desaparición del acceso invalidado. Son repeticiones
de escenarios del inventario de 53, no escenarios adicionales.

La revisión del formulario Admin añadió una regresión para campos de login ausentes:
el nuevo flujo MFA debe devolver errores de formulario en vez de acceder a un
usuario no autenticado. La suite final pasó 367 tests.

## Cierre local

Se detuvieron los servidores de QA y el clúster sintético, conservando sus datos.
Los registros de procesos `*-server` terminan por SIGTERM intencional y no son
comandos de tests fallidos. Se retiraron 692.971.413 bytes de cachés/downloads y
fixtures regenerables, preservando build standalone, dependencias y backups.
Las capturas elegidas, resultados y hashes quedan en oracle-evidence/2026-10-15.
Para repetir E2E, iniciar el clúster aislado y ejecutar nuevamente el seed.
