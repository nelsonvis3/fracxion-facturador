# Evidencia de Entrega 0 — 2026-10-14

Baseline del producto: `60753dc`. Ver [auditoría](../../ENTERPRISE_AUDIT.md) y [roadmap](../../ENTERPRISE_ROADMAP.md). Esta carpeta contiene resultados de ejecución, reproducciones y capturas; no implementa módulos de Fracxion.

## Lectura

- [checks.json](checks.json): 32 comprobaciones, argv ejecutado, cwd aislado, salida, código y duración. `log` conserva la ruta original de ejecución; `evidence_output` identifica la copia `.txt` aquí conservada. El valor sintético de clave de settings productivos se sustituyó por una etiqueta; no es una credencial de producción.
- [versions.json](versions.json) y [environment-capabilities.json](environment-capabilities.json): versiones ejecutadas y herramientas disponibles. PostgreSQL local **18.6**, Node **24**; Compose/CI declaran PostgreSQL 17/Node 22 y no se ejecutaron en esta entrega.
- [backend-suite.txt](backend-suite.txt), [coverage.txt](coverage.txt): 216 pruebas aprobadas; 91 % de cobertura de sentencias redondeado.
- [playwright-e2e-clean.txt](playwright-e2e-clean.txt): 35 pruebas aprobadas con API recién iniciada y sin tráfico de otras sondas. [Primer intento](playwright-e2e.txt): 33/35 por contador de login compartido con comprobaciones de esta auditoría. No se cambiaron ni eliminaron límites de seguridad para repetir.
- [probes-results.json](probes-results.json): consulta por línea, cobros repetidos sin referencia, ausencia de eventos auth y último propietario desde Admin. Un exit 0 de estas sondas **confirma el hallazgo**, no su solución.
- [roles-observations.json](roles-observations.json): 80/80 comprobaciones, cinco roles, inactivos/ajenos/relaciones mezcladas y comprobación de RLS. [Primer arnés](role-matrix.txt) tenía cinco expectativas 403 erróneas para anónimos; [corregido](role-matrix-corrected.txt) espera 401 según el contrato existente. Producto intacto.
- [browser-observations.json](browser-observations.json): 21 verificaciones de ancho, ocho inspecciones Axe, pageerrors y 5xx. Hay contraste insuficiente en Clientes. La bandera inicial de Tab fuera del diálogo se precisó con el siguiente registro.
- [focus-observations.json](focus-observations.json): Tab/Shift+Tab y cierre por Escape/Cancelar/botón. BODY recibe foco al cerrar; un intento de enfocar el fondo durante el modal no lo habilita.
- [restore-observations.json](restore-observations.json): pg_dump y pg_restore a base nueva de pruebas; diez tablas, 324 filas con conteos y hashes iguales. El dump y las bases sintéticas no se incluyen en el repositorio.
- [npm-audit-production-live.txt](npm-audit-production-live.txt), [npm-audit-all-live.txt](npm-audit-all-live.txt), [pip-audit-live.txt](pip-audit-live.txt): resultados efectivos con acceso de red. Los intentos sin sufijo `live` conservan los errores iniciales de red, no resultados negativos de vulnerabilidades.
- [production-build-webpack.txt](production-build-webpack.txt): build aprobado. Los otros registros de build distinguen el rechazo inicial de symlink de los fallos EPERM del entorno de Turbopack.
- [screenshots](screenshots/): cinco capturas de UI con datos exclusivamente sintéticos, generadas por Playwright. Son inspecciones puntuales, no una grabación de aceptación integral.
- `git-*-before.txt`, [untracked-before.json](untracked-before.json) e `integrity.json`: baseline y preservación del trabajo previo. `SHA256SUMS` permite verificar los archivos de esta entrega.

## Reproducción segura

La referencia de preparación es [TESTING.md](../../TESTING.md). Todos los comandos de esta auditoría se ejecutaron con Bash.

1. Crear una copia aislada de los archivos versionados del commit con `git archive`; no copiar `.env` privados ni usar la base configurada en el proyecto de trabajo.
2. Crear un cluster PostgreSQL independiente con `initdb`, directorio propio y puerto libre. En esta ejecución se utilizó `/tmp/fracxion-enterprise-audit-20261014/postgres`, `127.0.0.1:55439` y usuario sintético `audit`. La autenticación trust se limitó a esa instancia temporal en loopback; no es una propuesta de producción.
3. Configurar explícitamente DB_HOST/DB_PORT/DB_USER/DB_NAME/DB_SSLMODE, una DJANGO_SECRET_KEY sintética y `PYTHONDONTWRITEBYTECODE=1`. Para suite: `config.test_settings`, correo/caché en memoria y COVERAGE_FILE fuera del repositorio de trabajo.
4. Ejecutar los argv de `checks.json` desde backend/frontend de la copia; generar el schema y outputs en el directorio de evidencia. Para frontend, fijar `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001`; el build Webpack requiere dependencias físicamente dentro del árbol temporal. Typecheck antes de generar tipos reproduce F-06.
5. Para E2E crear **una base nueva** `test_facturador_e2e`, exportar `DJANGO_SETTINGS_MODULE=config.e2e_settings` y ejecutar `backend/scripts/seed_e2e.py`. El seed contiene credenciales públicas de fixture y genera un token sintético de recuperación; no reutilizarlo en ningún entorno comercial ni publicar su archivo de token.
6. Iniciar API en `127.0.0.1:8001` sin autoreload y frontend standalone en `127.0.0.1:3010`. Este último puerto es el origen permitido por e2e_settings. Para esta máquina se fijó `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/opt/brave-bin/brave`.
7. Ejecutar `npm run test:e2e` con API recién iniciada **sin otras sondas de login concurrentes**. Regenerar el fixture antes de repetir porque el token de recuperación es de uso único. No aumentar límites ni eludir CSRF para pasar las pruebas.
8. Las sondas Python adjuntas se copian al backend temporal y usan `config.e2e_settings`; requieren nombre de base y puerto guardados. `enterprise_probes.py` crea nombres únicos para esa ejecución inicial: repetir en entorno nuevo o adaptar nombres sintéticos sin borrar datos existentes. Las sondas Node se ejecutan desde frontend temporal con Playwright/Axe disponibles. No son pruebas permanentes integradas al CI.
9. `restore_probe.py` requiere psycopg y utilidades PostgreSQL; crea `test_facturador_enterprise_restore` y rechaza reutilizar implícitamente una base ya existente mediante el fallo de createdb. Ejecutarlo con flujos comerciales de prueba detenidos. No sustituir los nombres por bases comerciales.
10. Conservar resultados, detener exclusivamente los procesos de prueba y limpiar sus copias de dependencias/build. Nunca eliminar volúmenes, migraciones o datos preexistentes para repetir.

Los scripts contienen nombres y credenciales sintéticas de fixtures equivalentes a las ya presentes en la suite del proyecto. No contienen credenciales privadas leídas del entorno. Las trazas con tokens/cookies de prueba quedaron fuera de esta carpeta; los resultados y condiciones relevantes están documentados sin publicarlos.

## Límites

No se ejecutó infraestructura Docker/Redis/Caddy, SMTP real, Node 22, PostgreSQL 17, carga sostenida, auditoría de imágenes o una evaluación ASVS completa. Un check de settings productivos aprobado no es un despliegue ni una comprobación de entrega de correo. Un resultado Axe sin violaciones no acredita accesibilidad universal.

Se preservaron los documentos originales y el README previo sin seguimiento. Esta entrega añade documentación/evidencia; no cambia código de aplicación, dependencias ni migraciones.
