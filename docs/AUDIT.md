# Auditoría y validación

Revisión iniciada el 9 de octubre de 2026 sobre el código local. El informe de continuidad se utilizó como contexto; los resultados previos se contrastaron con los archivos y pruebas actuales.

**Continuación del 10 de octubre:** el [log de errores y correcciones](AUDIT_LOG.md) documenta los hallazgos nuevos y la validación vigente: 216 pruebas backend, 91% de cobertura y quince escenarios Playwright tras corregir el dashboard y aclarar el selector de facturas al registrar pagos. Incluye capturas y comprobaciones de escritorio/móvil. Las tablas de este informe conservan los resultados de la revisión inicial.

## Diagnóstico inicial

- `accounts/views.py`: el listado de empresas omite `Membership.is_active`.
- `accounts/views.py`, `frontend/src/lib/api.ts`: el bootstrap CSRF solo entrega una cookie; JavaScript en otro host no puede leerla. El login rota el secreto CSRF.
- `accounts/views.py`: el login no limita intentos.
- `billing/services.py`: la creación directa de borradores no verifica membresía; las otras operaciones sí lo hacen.
- `billing/models.py`: catálogo permite 12 dígitos enteros de precio; las líneas solo admiten 10. Cantidades y precios individualmente válidos pueden exceder los totales `numeric(16,2)`.
- `customers/views.py`, `catalog/views.py`: las actualizaciones leen objetos sin bloqueo y pueden perder cambios concurrentes o auditar valores anteriores desactualizados. Las carreras de unicidad pueden devolver 500.
- `customers/serializers.py`: elimina letras de documentos numéricos antes de validarlos; la provincia argentina se duplica en dos catálogos. El frontend aplica reglas de teléfono, DNI y códigos postales diferentes.
- `customers/tests.py`: una prueba está definida dos veces y una definición queda oculta.
- Frontend: permisos de escritura ausentes en clientes, recuperación enlazada a páginas inexistentes, productos/facturas/pagos/auditoría sin interfaz.
- Despliegue: falta servidor WSGI, archivos estáticos, caché compartida, configuración HTTPS por entorno, ejemplos de variables, health checks, CI y documentación propia. Metadatos e idioma del frontend conservan los valores de Next.js.

## Línea base

- Django: 143 pruebas pasan en PostgreSQL temporal, aislado de los datos locales.
- `manage.py check`: sin errores.
- TypeScript: pasa.
- ESLint: una advertencia por importación sin uso.
- Build inicial: Turbopack bloqueado por los permisos de red del sandbox; se reintenta fuera de él.

## Correcciones entregadas

- **Sesión y CSRF:** token enmascarado por JSON, renovación antes de escrituras, cookies HttpOnly, respuesta tras la rotación del login, distinción 401/403 y redirección de sesiones vencidas. El listado de empresas excluye membresías inactivas.
- **Registro público:** `/register` y `/api/auth/register/` crean una cuenta normal, su empresa y membresía de propietario, con auditoría transaccional y sesión automática. Validan contraseña y confirmación, correo único normalizado y campos; rechazan privilegios y empresas ajenas. Veinte pruebas adicionales comprueban rollback, CSRF, límites y la carrera real de dos registros con el mismo correo.
- **Permisos:** los servicios de borradores verifican el actor y su rol dentro de la transacción. Las interfaces de cada módulo respetan owner/admin/accountant/sales/viewer; la API mantiene la comprobación definitiva. Cambiar de empresa reinicia el contexto del frontend.
- **Integridad:** precisión de líneas compatible con el catálogo, validación de importes finitos y límites de almacenamiento, monedas ISO, límites de cantidad y referencias de pagos. Las actualizaciones bloquean el registro antes de leer/validar; conflictos de documento/SKU devuelven 400 en lugar de 500.
- **Datos y consultas:** catálogo único de provincias argentinas, rechazo de letras y dígitos Unicode en documentos numéricos, snapshots de país/código postal y saldo agregado sin consultas por cada factura. Los pagos devuelven su moneda y referencia de documento.
- **Frontend:** catálogo, borradores, emisión, impresión, pagos, reversión, auditoría y recuperación completos. Selectores con búsqueda/paginación, estados de carga y reintento, validación definitiva del backend y PATCH solo de campos modificados. Desactivación/reactivación de clientes y catálogo.
- **Construcción:** integración estándar de Tailwind mediante PostCSS; eliminación de dependencias sin uso y fuentes remotas. Servidor standalone con assets incorporados, metadatos españoles y branding propio.
- **Operación:** imágenes sin usuario root, Gunicorn, estáticos WhiteNoise, PostgreSQL/Redis privados, Caddy HTTPS, validación de entorno de producción, IP de cliente solo desde proxy confiable, endpoints de salud y readiness, creación de propietario y Admin adaptado al usuario por email.
- **Contrato y mantenimiento:** esquema OpenAPI corregido y validado, requisitos de desarrollo separados, CI, pruebas reproducibles y documentación de instalación, operación y alcance comercial.

La migración nueva `billing.0003` amplía el precio de línea y agrega snapshots opcionales. No reescribe documentos anteriores; debe aplicarse durante el release. Las bases reales existentes no se modificaron durante esta revisión.

## Verificación final

| Nivel | Evidencia local |
| --- | --- |
| Backend funcional | 203 pruebas aprobadas sobre PostgreSQL temporal. Se crean y eliminan bases de tests separadas. |
| Concurrencia | Pruebas con conexiones y threads independientes para numeración, pagos y referencias; sin recurrir a SQLite. |
| Cobertura | 91% de sentencias: 1.962 sentencias, 184 sin ejecutar. Excluye los propios tests, migraciones, configuración E2E y entrypoints. No es cobertura de ramas. |
| Estático | Ruff y formato aprobados; ESLint sin advertencias; TypeScript validado por el build. |
| Contrato | `spectacular --validate --fail-on-warn` aprobado sin advertencias. |
| Esquema de base | `makemigrations --check --dry-run`: sin cambios pendientes. Migraciones aplicadas en las bases aisladas y el stack Docker. |
| Frontend | Build optimizado con Next.js 16.4.0 aprobado y arranque standalone comprobado. |
| Navegador | Seis escenarios Chromium aprobados, descritos abajo. |
| Empaquetado | Ambos Dockerfiles construidos con instalaciones reales de dependencias. |
| Runtime de producción | Stack local aislado: PostgreSQL y Redis saludables, Gunicorn y Next standalone detrás de Caddy HTTPS. Registro con empresa/owner, escritura con CSRF renovado, persistencia, login/logout, CSRF obligatorio, cookies Secure/HttpOnly, páginas y assets, estáticos Admin y `/health/`/`/ready/` comprobados. |
| Configuración de producción | `manage.py check --deploy --fail-level WARNING` sin problemas en el contenedor. |
| Exclusión de datos privados | Entornos locales, venv, node_modules, builds, cobertura, trazas y token E2E están ignorados por Git. Los ejemplos de entorno se incluyen. |

### Escenarios de navegador

1. Propietario: crear cliente, editar y recargar, desactivar/reactivar, crear servicio, guardar borrador, emitir, registrar pago, recargar, revertir y consultar auditoría. Precio 100, impuesto 21%, total 121; pago 40, saldo 81; reversión, saldo 121. Valores sintéticos.
2. Viewer: consulta sin escritura, auditoría denegada y empresa ajena inaccesible.
3. Sesión eliminada: retorno al login.
4. Recuperación genérica, cambio con token real y rechazo de reutilización.
5. Navegación en viewport de 390 px sin desbordamiento horizontal de la página de catálogo.
6. Registro móvil: errores de contraseña y confirmación, cuenta/empresa/propietario, creación de cliente, correo duplicado, logout/login y bloqueo de acceso a otra empresa.

Captura inspeccionada: [factura interna](screenshots/invoice.png). Estas pruebas usan una API real y PostgreSQL, sin mocks de respuestas comerciales. No prueban todos los módulos en todas las resoluciones ni impresión en cada navegador.

## Dependencias y aviso pendiente

- `pip-audit`: sin vulnerabilidades conocidas en el entorno Python revisado.
- `npm audit --omit=dev`: cero vulnerabilidades reportadas.
- `npm audit`: cinco paquetes de desarrollo afectados por una cadena que termina en `braces@3.0.3`: `eslint-config-next → @next/eslint-plugin-next → fast-glob → micromatch → braces`.

El aviso [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) describe agotamiento de pila con patrones profundamente anidados. La consulta al registro durante la revisión devolvió 3.0.3 como última versión de `braces`; npm propone bajar `eslint-config-next` a 14.2.35. No se aplicó ese cambio de versión ni se ocultó el aviso con overrides. Esta cadena corresponde a herramientas de desarrollo; la auditoría de producción pasa. Revalidar el registro y la configuración de ESLint cuando exista una corrección compatible.

## Límites de esta entrega

La aplicación implementa facturación **interna**; no ARCA, CAE, notas de crédito/débito ni validación de identidad contra organismos. El registro crea una empresa propia; no incluye invitaciones ni verificación de correo mediante enlace. Tampoco incorpora inventario, conciliación bancaria o facturación de planes SaaS.

La prueba Docker usa un dominio local y certificado local de Caddy. No acredita DNS/certificados públicos, entrega SMTP real, backups externos, pruebas de carga, alta disponibilidad o aceptación con datos y usuarios de negocio. El workflow de GitHub Actions está configurado, pero no se ejecutó en GitHub. Los pasos para completar esas verificaciones están en [OPERATIONS.md](OPERATIONS.md).

Las reglas de inmutabilidad y aislamiento se aplican en las API, los servicios y controles de modelos. Acceso SQL directo o `QuerySet.update` puede saltar controles de aplicación; por eso nuevas integraciones deben usar los servicios y restringir las credenciales de base.
