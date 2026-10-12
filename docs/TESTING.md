# Pruebas reproducibles

Usar una base separada y datos sintéticos. No ejecutar pruebas de navegador sobre una empresa real. Django crea y elimina su propia base para los tests del backend; el script E2E solo acepta una configuración de pruebas y un nombre de base que empiece con `test_`.

## PostgreSQL temporal

Desde la raíz, con Docker disponible:

```sh
docker run -d --name facturador-tests -p 127.0.0.1:55433:5432 -e POSTGRES_PASSWORD=synthetic-test-only -e POSTGRES_DB=postgres postgres:17
docker exec facturador-tests pg_isready -U postgres
```

Esperar a que PostgreSQL esté disponible antes de continuar. El nombre y puerto distinguen esta instancia de la base local. El usuario del contenedor puede crear las bases que requiere Django.

## Backend

Instalar `requirements-dev.txt` y preparar `backend/.env` como indica el README. Desde `backend/`:

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python manage.py check
env DB_NAME=postgres DB_USER=postgres DB_PASSWORD=synthetic-test-only DB_HOST=127.0.0.1 DB_PORT=55433 .venv/bin/python manage.py makemigrations --check --dry-run
env DB_NAME=postgres DB_USER=postgres DB_PASSWORD=synthetic-test-only DB_HOST=127.0.0.1 DB_PORT=55433 .venv/bin/python manage.py spectacular --validate --fail-on-warn --file /tmp/facturador-schema.yaml
env DB_NAME=postgres DB_USER=postgres DB_PASSWORD=synthetic-test-only DB_HOST=127.0.0.1 DB_PORT=55433 .venv/bin/coverage run manage.py test --settings=config.test_settings --noinput
.venv/bin/coverage report --fail-under=85
.venv/bin/pip-audit -r requirements.txt
```

Tests usan correo en memoria, caché local y hashing rápido exclusivamente para pruebas. Conservan PostgreSQL para comprobar restricciones y concurrencia. La cobertura excluye tests, migraciones y configuraciones de E2E.

## Frontend y E2E

Desde la raíz, crear la base E2E una vez:

```sh
docker exec facturador-tests createdb -U postgres test_facturador_e2e
```

Desde `backend/`, preparar las cuentas y arrancar la API:

```sh
env DJANGO_SETTINGS_MODULE=config.e2e_settings DB_NAME=test_facturador_e2e DB_USER=postgres DB_PASSWORD=synthetic-test-only DB_HOST=127.0.0.1 DB_PORT=55433 .venv/bin/python scripts/seed_e2e.py
env DB_NAME=test_facturador_e2e DB_USER=postgres DB_PASSWORD=synthetic-test-only DB_HOST=127.0.0.1 DB_PORT=55433 .venv/bin/python manage.py runserver 127.0.0.1:8001 --settings=config.e2e_settings --noreload
```

Desde `frontend/`, en otra terminal:

```sh
npm ci
npm run lint
npm run typecheck
npm audit --omit=dev
npx playwright install chromium
env NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 npm run build
env PORT=3010 HOSTNAME=127.0.0.1 npm run start
```

Con ambos servidores disponibles, ejecutar desde una tercera terminal en `frontend/`:

```sh
npm run test:e2e
```

Si el navegador se instala en un directorio temporal, utilizar el mismo `PLAYWRIGHT_BROWSERS_PATH` en instalación y ejecución; la revisión local usó `/tmp/facturador-playwright`. Por ejemplo: `PLAYWRIGHT_BROWSERS_PATH=/tmp/facturador-playwright npx playwright install chromium` y `PLAYWRIGHT_BROWSERS_PATH=/tmp/facturador-playwright npm run test:e2e`.

Los quince escenarios comprenden once flujos de navegador y cuatro de seguridad API. Verifican el ciclo comercial con persistencia, viewer y aislamiento, sesión vencida, recuperación con reutilización inválida del token, navegación móvil y registro público. El registro prueba contraseña débil, confirmación incorrecta, alta con empresa y permisos de propietario, escritura con el CSRF renovado, correo duplicado, logout/login e inaccesibilidad de otra empresa. La regresión de logout comprueba que no queden datos privados en páginas ocultas, tanto al salir desde una empresa como desde el selector, ni al volver con el historial.

`e2e/dashboard.spec.ts` comprueba selector y resumen de empresa a 1440/768/390/320 px, sin desbordamiento horizontal, con contraste legible en preferencia oscura/clara y movimiento reducido. Navega desde la tarjeta de empresa con teclado hasta un módulo y compara los cuatro contadores con la API real. Comprueba accesos de viewer y los estados de carga, error/reintento y lista vacía mediante respuestas controladas de navegador; el reintento vuelve a consultar la API real.

`e2e/payments.spec.ts` crea una empresa nueva de prueba: comprueba el selector sin emitidas, que un borrador no aparezca, su emisión desde UI y la opción con cliente/saldo. Prueba una búsqueda sin coincidencias y registra desde Pagos un cobro parcial de 40,00 sobre 121,00; verifica persistencia y saldo 81,00 en la API.

Los escenarios API comprueban CSRF, origen ajeno, CORS, caché privada, privilegios falsificados, aislamiento de datos y relaciones entre dos empresas reales de prueba, y entrada malformada contra el servidor en ejecución. `e2e/fixtures.ts` hace fallar cada flujo de navegador si aparece una excepción JavaScript o una respuesta 5xx. Chromium puede necesitar bibliotecas del sistema: CI utiliza `npx playwright install --with-deps chromium`.

El script genera `frontend/e2e/reset-fixture.json`, ignorado por Git y excluido de Docker. Antes de repetir la suite, ejecutar otra vez `seed_e2e.py` para regenerar la contraseña y el token consumido. Los tests dejan operaciones sintéticas; la selección usa búsqueda para no depender de la primera página. Reiniciar la API de pruebas si varias ejecuciones agotan los límites de login o registro del caché local.

Los fallos guardan trazas en `frontend/test-results/`. Los flujos aprobados generan `docs/screenshots/invoice.png`, `payment-selector.png` y las capturas `dashboard-{desktop,mobile}.png` y `company-dashboard-{desktop,mobile}.png`; son evidencia de prueba, no capturas de producción. Un build E2E incorpora la URL del puerto 8001: volver a compilar con el entorno definitivo antes de desplegar. Docker realiza su propio build.

Las regresiones del 10 de octubre están en `accounts/test_security.py` y `config/test_security.py`. Cubren entradas excesivas, Unicode/NUL, tamaño/profundidad JSON, búsqueda, límites de credenciales y rechazo de configuración insegura de producción. El diagnóstico, corrección y resultados se conservan en [AUDIT_LOG.md](AUDIT_LOG.md).

## CI y alcance

`.github/workflows/ci.yml` ejecuta dos jobs con PostgreSQL: backend y frontend/E2E. El umbral de cobertura es 85%. La auditoría de npm de producción es obligatoria; los avisos de desarrollo se documentan en `AUDIT.md`.

Estas comprobaciones no sustituyen pruebas de carga, SMTP real, backups externos ni aceptación por usuarios de negocio. Al finalizar, detener los servidores temporales. El contenedor `facturador-tests` puede detenerse con `docker stop facturador-tests`; conservar o eliminar sus datos según se necesiten nuevas ejecuciones.
