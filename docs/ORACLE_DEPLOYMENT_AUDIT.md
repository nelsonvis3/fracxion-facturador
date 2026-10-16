# Auditoría previa al despliegue Oracle

Fecha: 2026-10-15. Estado: preparación local; **sin despliegue público**.

## Versión y control de cambios

El repositorio correcto es `/home/nelson/Proyectos/facturador-saas-api`.
`main` y el HEAD público por HTTPS coincidían en
`2ad91d706d3c6f4b1b894c59b5d3b55bc95a25e6` al comenzar. El árbol estaba limpio;
por tanto todos los cambios de esta revisión se distinguen de ese commit.
La última CI pública de ese HEAD terminó correctamente:
[ejecución 38784542087](https://github.com/nelsonvis3/fracxion-facturador/actions/runs/38784542087).
Esa ejecución no valida los cambios locales posteriores.

El acceso Git por SSH falló por permisos de una configuración de SSH del sistema.
Se contrastó el HEAD mediante HTTPS, sin cambiar SSH ni credenciales. No se hizo
push, commit nuevo, cambio DNS ni modificación remota. El commit definitivo está
pendiente: no desplegar el HEAD base omitiendo estos cambios sin revisión.

## Arquitectura encontrada

| Servicio | Código/configuración real | Persistencia y función |
| --- | --- | --- |
| database | PostgreSQL 17 Bookworm | `postgres_data`; dominio, sesiones, auditoría, jobs y archivos binarios privados. |
| cache | Redis 8 Bookworm | Límites compartidos de autenticación; 128 MiB, `noeviction`. No contiene la fuente de verdad de trabajos. |
| backend | Python 3.14, Django 5.2.18, DRF 3.18.1, Gunicorn | Servicios de negocio explícitos; WhiteNoise para estáticos. |
| worker | La misma imagen Django, `manage.py run_jobs` | Cola PostgreSQL, leases, reintentos y scheduler integrados. Sin Celery ni Beat. |
| frontend | Node 22, Next 16.4.0, React 19.3.0 | Standalone; API del mismo origen en Docker. |
| proxy | Caddy 2 | HTTPS automático; `caddy_data` y `caddy_config`. |

La revisión del código incluyó accounts/tenancy/customers/catalog/billing/auditlog,
analytics/reports/automation/operations, configuración, Compose, CI y frontend.
Los módulos comerciales existentes conservan cálculos Decimal y sus servicios.
Logos, adjuntos de gastos y resultados privados de reportes están en PostgreSQL:
no hay un directorio media adicional que deba inventarse para este despliegue.

## Correcciones y preparación en esta revisión

- MFA TOTP opcional completo: alta confirmada, secretos Fernet, recuperación con
  hashes, rechazo de repetición, locks PostgreSQL, expiración, login API y Admin,
  invalidación de sesiones y pantalla de gestión. Migración aditiva accounts 0004.
- Aviso `braces` eliminado del árbol real de dependencias mediante un alias npm
  acotado a `@next/eslint-plugin-next > fast-glob`, usando tinyglobby 0.2.17.
  Se conserva el plugin oficial y sus reglas; un contrato prueba que rechaza
  enlaces internos incorrectos con raíces literales, glob y arrays.
- `requirements.lock` fija las 34 versiones de producción, incluidas transitivas;
  se comprobaron contra el entorno que ejecuta los tests y las ruedas ARM64.
- Overlay `compose.oracle.yaml`: ARM64, límites de recursos, logs acotados,
  healthcheck frontend y orden de inicio. El Compose resuelto solo publica Caddy.
- HSTS se limita al host hasta conocer el dominio; sin preload ni includeSubDomains.
  Swagger/esquema públicos se excluyen de las URLs de producción.
- Scripts de preflight y backup cifrado externo, timer preparado sin instalar.

## Resultados y bloqueos

Los resultados detallados y los intentos fallidos se conservan en
[ORACLE_DEPLOYMENT_TESTING.md](ORACLE_DEPLOYMENT_TESTING.md). No se consideran
pruebas de producción los tests nativos con PostgreSQL 18.6, caché local y Node 24.

Las imágenes oficiales publican manifiestos linux/arm64. Se descargaron las ruedas
Python y se instaló el árbol npm para ARM64 sin ejecutar scripts/binarios ARM.
Falta construir y ejecutar realmente las imágenes en A1; no se afirma compatibilidad
operativa completa solo por estos controles.

No hay Docker Engine, CLI OCI, `~/.oci/config` ni alias SSH configurados. No se ha
confirmado cuenta OCI, región principal, cuotas, recursos existentes, VM, IP,
dominio controlado, SMTP entregable ni repositorio externo de backup.

El check Django de despliegue con valores desechables produce únicamente W005 y
W021 por la decisión HSTS de alcance limitado. El comando estricto con
`--fail-level WARNING` queda registrado como fallido; no se silencian las alertas
ni se declara que pasó. La política definitiva se revisará con el dominio real.

API keys, webhooks y suscripciones siguen como diseño en SAAS_PRODUCT_POLICY.md;
no son necesarios para una demo cerrada de portfolio ni se anuncian terminados.
Recordatorios por correo a clientes, pagos SaaS e integración fiscal no se activan.

## Primer punto de intervención

Confirmar si existe cuenta OCI activa y su **Home region**, sin compartir claves.
Después revisar juntos **Limits, Quotas and Usage**, instancias y volúmenes de esa
región. Solo entonces presentar la aprobación A con configuración y costos
reales. La configuración candidata está en ORACLE_INFRASTRUCTURE.md.
