# Fracxion — roadmap empresarial propuesto

Fecha: 2026-10-14. Baseline: `60753dc`. Estado: **aprobado y en ejecución local**.

El propietario aprobó continuar y luego amplió la instrucción: trabajar de forma continua, sin detenerse para presentar/aprobar cada entrega, revisar el proyecto completo y ejecutar pruebas reales y simulaciones adversariales controladas. Las agrupaciones siguientes organizan el trabajo; ya no son puntos de parada. Se mantienen las restricciones sobre datos existentes, publicación, costos externos e integraciones reales, y se documentan decisiones comerciales que no puedan inferirse con seguridad.

Este plan deriva de [ENTERPRISE_AUDIT.md](ENTERPRISE_AUDIT.md) y sus reproducciones. Mantiene Django como monolito modular, Next.js, PostgreSQL y la lógica comercial existente. La tabla original conserva las prioridades de diseño; varios módulos ya existen. El estado actual se registra abajo y en CHANGELOG/TESTING. No incluye despliegue, servicios pagos ni activación de envíos reales.

## Orden propuesto y prioridades

P1: continuidad, autorización, trazabilidad y fundamento empresarial. P2: fiabilidad, eficiencia y experiencia de uso. P3: expansión posterior con requisitos definidos. Los bloques 0.1 y 1 constituyen la primera implementación recomendada; no se proponen todas las fases en un cambio masivo.

| Entrega / prioridad | Trabajo concreto | Archivos afectados propuestos | Dependencias | Riesgos | Criterio de aceptación |
| --- | --- | --- | --- | --- | --- |
| 0.1 / P1 | Proteger último owner y auditar cambios desde Admin | `backend/tenancy/services.py` nuevo, `tenancy/admin.py`, `accounts/admin.py` si corresponde, tests tenancy/auditlog | F-01/F-02; definir excepción de plataforma explícita | Bloqueo accidental de soporte; carrera entre cambios y usuarios desactivados | Dos cambios concurrentes no dejan empresa sin owner; rollback si auditoría falla; log Admin y empresarial coherentes. |
| 0.1 / P1 | Eventos de seguridad y revisión de protección de acceso privilegiado | `backend/accounts/views.py`, `password_reset.py`, `rate_limits.py`, `auditlog/services.py`, tests | F-05; alcance/retención de eventos | Filtrar tokens/PII, crecimiento ilimitado o contar éxito como ataque | Eventos mínimos sin secretos; login/logout/reset/denegación relevantes probados; decisión documentada para Admin y límites por cuenta. |
| 0.1 / P2 | Resolver preparación del typecheck y documentar aislamiento E2E | `frontend/package.json`, `.github/workflows/ci.yml`, `docs/TESTING.md`; arnés solo si hace falta | F-06; suite limpia 35/35, primer intento contaminado por sondas de auditoría | Ocultar regresiones al relajar seguridad o aumentar timeouts | Typecheck desde checkout limpio; API dedicada para E2E; mantener límite productivo y tests de bloqueo. No hay defecto de transición demostrado por el primer intento. |
| 0.1 / P2 | Contraste y foco con cambios puntuales | `frontend/src/app/dashboard/[tenantId]/customers/page.tsx`, `components/business-ui.tsx`, E2E | F-08/F-09; reproducción de foco | Alterar UX visual ya operativa | Contraste AA del texto afectado; Enter/Tab/Shift+Tab/Escape y retorno al disparador; responsive sin regresiones. |
| 0.1 / P2 | Agrupar validación de productos al emitir | `backend/billing/services.py`, `billing/test_regressions.py` | F-03; preservar contratos financieros | Relajar aislamiento, snapshots o bloqueos | Pruebas monetarias/tenant/concurrencia pasan; consultas no crecen una por línea. |
| 0.1 / P2 | Tratar advisory del tooling sin cambios mayores forzados | `frontend/package-lock.json` y manifest solo si solución compatible | F-07; versión corregida compatible disponible | Downgrade incompatible de Next/ESLint | Producción sigue sin alertas; herramienta compatible validada o excepción temporal documentada con alcance y revisión. |
| 1A / P1 | Business Settings por empresa | `backend/tenancy/models.py`, serializers/views/urls/services nuevos; `config/urls.py`; `frontend/.../[tenantId]/settings/page.tsx`, navegación/cliente API; tests | Base tenant actual, política de archivos y permisos | Filtración de logo, introducir conversiones o cambiar históricos | Settings aislados; owner/admin autorizados; cambios auditados; validación de país/zona/moneda; logo con límites y acceso probado. |
| 1B / P1 | Equipo e invitaciones | `backend/tenancy/models.py`, services/serializers/views/permissions; correo controlado; `frontend/.../team/page.tsx`; tests | 0.1 y 1A; política de roles/cuenta existente | Toma de cuenta, escalada, token reutilizado, último owner | Tokens seguros/hash/expiración/uso único; resend/revoke; permisos backend; concurrencia; UI completa; ningún endpoint concede staff/superuser. |
| 1C / P1 | Vencimientos y cuentas por cobrar básicas | `backend/billing/models.py`, `services.py`, `serializers.py`, `views.py`, migración aditiva; formularios/listados frontend; tests | Regla de vencimiento antes de emisión; moneda/zona de empresa | Mutar emitidas o inventar mora histórica | `due_date` nullable histórico; fecha definida en borrador; emitidas inmutables; mora calculada solo con fecha válida y saldo positivo; filtros reales. |
| 2A / P1 | Agregación empresarial y KPIs | `backend/analytics/` propuesto, urls/settings, tests; `frontend/.../analytics/page.tsx`, cliente API | 1C y definición de períodos/monedas | Doble conteo por joins, mezclar cobros/ventas o monedas | Agregados Decimal separados por moneda; exclusión de borradores y reversiones según contrato; bordes de fecha y comparación verificables. |
| 2B / P2 | Gráficos y filtros conectados | Servicios analytics; componentes de gráficos y formularios | 2A; elegir librería solo si necesaria | Gráfico estático, métricas contradictorias o payload costoso | Cambiar fecha/cliente/estado/moneda modifica consultas y resultado; estados vacíos/errores accesibles; presupuesto de consultas medido. |
| 2C / P1 | CSV, XLSX y PDF seguros | `backend/reports/` propuesto, API/downloads, tests; UI reportes | 2A; evaluar bibliotecas mínimas; cola para trabajos costosos | Acceso entre tenants, fórmulas, agotamiento de recursos, enlaces filtrados | Archivos incluyen empresa/período/moneda/fecha; autorización en generación y descarga; fórmula neutralizada; límites; expiración; descarga probada. |
| 3A / P1 | Evaluación técnica de worker y outbox | Prueba aislada de compatibilidad, luego `config/celery.py` si aprobado, `automation/`, Compose, requirements; tests | Python 3.14; versión estable soportada; broker separado | Adoptar stack sin soporte, perder tareas o afectar límites de auth | Matriz de versiones y prueba real worker/broker/DB; no adoptar prerelease sin decisión; fuente durable en PostgreSQL para efectos importantes. |
| 3B / P1 | Idempotencia de operaciones que admitan reintentos | `backend/billing/services.py`, contrato API y almacenamiento de claves propuesto; tests | F-04; diseño compatible aprobado | Duplicar cobros o descartar dos pagos válidos | Misma clave/payload produce un efecto; contenido distinto da conflicto; concurrencia y timeout cubiertos; solicitudes sin clave conservan contrato. |
| 3C / P1 | Recordatorios, notificaciones e informes programados | `automation/`, `notifications/`, servicios reports; `frontend/.../automations`, notificaciones | 1C, 2C, 3A/B y preferencias/envíos autorizados | Spam, duplicados, tarea con tenant equivocado, pérdida tras caída | `on_commit` + outbox cuando proceda; ejecución/reintentos/timeouts; claves únicas; preferencias; worker caído y recuperación probados; correo de tests. |
| 4A / P3 | Proveedores, compras y gastos | Módulos propuestos `suppliers/`, `expenses/`, UI y tests | Diseño de datos y flujo aprobado; adjuntos seguros | Confundir compra, recepción, deuda y pago; inventar contabilidad | Relaciones por empresa; desactivación histórica; importes/impuestos/estados definidos; auditoría y reportes integrados. |
| 4B / P3 | Inventario por movimientos | `inventory/` propuesto, servicios/constraints/tests; UI | Diseño funcional aprobado; regla de reservas/entregas | Stock negativo por concurrencia; descontar por factura sin regla | Libro de movimientos, ajustes con motivo, bloqueo transaccional; frontend no escribe stock; reglas y alertas probadas. |
| 5A / P1 antes de integrar | Credenciales limitadas y webhooks | `integrations/` propuesto, API/docs/tests | Scopes, eventos y contratos aprobados; 3A/B | SSRF, secretos expuestos, replay, eludir servicios comerciales | Keys con hash/revocación/scopes/tenant; firma y límites de destino; reintentos/idempotencia; historial seguro; sin conexión externa real no autorizada. |
| 5B / P1 continuo | Seguridad y operación empresarial | accounts/config/deploy/CI, docs, tests | Prioridad por riesgo; infraestructura de destino | Bloqueo de usuarios, costo externo, rollback incompatible | Verificación email/sesiones/MFA privilegiado progresivos; backup externo y restore verificado; logging/alertas; pruebas PG17/Redis8/Node22/HTTPS. |
| 6 / Decisión comercial | Diseño de planes, límites y suscripciones | Documento comercial/arquitectónico; código solo tras aprobación específica | Precios, proveedor, límites, trial, retención, soporte | Costos y restricciones inesperadas a usuarios actuales | Entitlements separados de roles; política de suspensión/exportación; no activar pasarelas ni bloquear funciones actuales sin acuerdo. |

## Diseño funcional de la Entrega 1

### Configuración por empresa

Reutilizar `Tenant.name`, `legal_name` y `tax_id`. Evaluar campos adicionales en Tenant frente a una relación uno a uno de preferencias según tamaño/responsabilidad; no duplicar datos existentes. Modelar país ISO, zona IANA validada, moneda ISO por defecto, contacto y términos/preferencias de comprobante. La moneda predeterminada es un valor para nuevos documentos, no una conversión de importes existentes.

Lectura solo para membresías autorizadas; escritura owner/admin con una política explícita para campos sensibles. Actor y empresa se obtienen de sesión y ruta, nunca del payload. Cambios auditados con valores antes/después y sin secretos.

El logo necesita tipo real, tamaño máximo, dimensiones/límites de procesamiento y almacenamiento definido. Evitar SVG activo sin sanitización demostrada. Definir quién puede verlo y probar URL/descarga con otra empresa; no confiar solo en ocultar la imagen en la interfaz. No elegir un servicio externo pago por defecto.

### Equipo

Usar `Membership` para usuarios ya registrados. Una invitación debe registrar empresa, email normalizado, rol solicitado, invitador, expiración, estado, hash del token y marcas de aceptación/revocación. Token aleatorio seguro; almacenar hash, no token de acceso legible. Resend rota/invalida el anterior y respeta límites. La aceptación confirma el control de identidad destinataria según el flujo acordado y no añade privilegios de plataforma.

Regla propuesta para aprobar junto con la entrega: owner administra propietarios; admin administra accountant/sales/viewer sin promover ni modificar owners o conceder privilegios iguales/superiores por cuenta propia. Si el negocio desea otra matriz, resolverla antes de implementar esa porción. Autorizar siempre en Django y revalidar dentro de la transacción.

Preservar al menos un propietario con cuenta y membresía activas. Los cambios de membresía, de rol y la desactivación del usuario que representa al último owner deben seguir la misma invariante. El soporte de plataforma tendrá una excepción solo mediante procedimiento explícito autorizado, con auditoría y sin endpoint empresarial de escalada.

### Vencimientos y cartera

`Invoice.due_date` nullable es la propuesta inicial; usar una fecha de negocio y condiciones de pago como snapshot al crear el borrador. Reutilizar `balance`/`paid_total` existentes, no mantener otro saldo mutable en paralelo. Crear vencimiento antes de emitir; si se habilita edición de borrador, será un endpoint explícito limitado a campos admitidos, con permisos/auditoría y rechazo después de emisión.

Para históricos, `NULL` significa **sin vencimiento informado**. Nunca inferir vencimiento desde `created_at`, imponer retrospectivamente términos nuevos o marcar esos documentos como atrasados. `overdue` requiere emitida, saldo positivo y fecha anterior al día de la empresa; definir si el día del vencimiento todavía está en plazo. Saldo cero no está vencido aunque la fecha haya pasado. Cambios de preferencias no reescriben documentos emitidos.

Filtros propuestos: vencida, próxima a vencer, sin fecha, rango de vencimiento, cliente, moneda y saldo pendiente. El criterio de “próxima” debe mostrarse explícitamente. Historial de recordatorios se incorporará con la Entrega 3, no como indicador ficticio en esta fase.

## Diseño de analítica y reportes

Establecer contratos antes de construir gráficos:

| Indicador | Fuente y regla propuesta |
| --- | --- |
| Facturado | Suma de total de facturas internas emitidas, por `issued_at`, agrupada por moneda. Borradores y notas sin flujo no participan. |
| Cobrado efectivo | Pagos por `received_at`, excluyendo los revertidos según la vista actual; moneda heredada de la factura. No llamarlo ventas ni ingresos contables devengados. |
| Saldo actual | Total emitido menos cobros efectivos de la misma factura; reutilizar semántica actual. |
| Saldo vencido | Saldo positivo de documentos con due_date válida anterior a la fecha de negocio. Sin vencimiento informado se presenta separado. |
| Cantidades | Documentos y clientes con criterios visibles; “cliente activo” significa estado activo, salvo que se acuerde otra definición de actividad comercial. |
| Evolución/comparación | Límites temporales normalizados a la zona empresarial, intervalo semiabierto y período anterior comparable, sin sumar monedas. |

Los reportes actuales y los históricos “al cierre de una fecha” son distintos. Para reconstruir cartera al cierre, considerar fecha de emisión, recepción y momento de reversión; no usar sin más el saldo actual filtrado por fecha. Aprobar la semántica de pagos retroactivos, reversiones y períodos antes de afirmar que hay cierre financiero histórico.

Evitar multiplicar totales al unir líneas y pagos. Probar facturas de varias líneas con múltiples cobros, reversión posterior, cero resultados, decimales límite, varias monedas y zonas/fechas límite. Usar subqueries/agregaciones separadas si corresponde, medir SQL y EXPLAIN con volumen sintético representativo antes de índices/caché. No agregar caché sin invalidación definida ni WebSockets por presentación.

Los reportes cubrirán ventas, cobros, cartera, movimientos de cliente, producto y resumen financiero **interno**. CSV primero permite una entrega pequeña; XLSX/PDF después de evaluar dependencias compatibles. Neutralizar fórmulas iniciadas por caracteres relevantes, incluidos espacios/control inicial, en texto de usuario. Limitar filas/tiempo/tamaño. Trabajos costosos tendrán registro persistente de generación, permisos revalidados al descargar y expiración; no una URL pública permanente.

## Automatización: decisión técnica revisada

La [historia oficial de Celery 5.6](https://docs.celeryq.dev/en/stable/changelog.html) anuncia **soporte inicial de Python 3.14**. La tabla de versiones y los classifiers que se consultaron en la auditoría inicial no bastaban para concluir incompatibilidad; se corrige esa conclusión. No se ha ejecutado aquí la combinación Celery/Redis/Django en procesos reales.

Para los dos tipos iniciales de trabajo (informes acotados y avisos internos), se implementa una cola durable dentro del monolito sobre PostgreSQL, con `select_for_update(skip_locked=True)`, concesiones con UUID y vencimiento, proceso separado con timeout de ocho minutos, tres intentos, backoff y registros por intento. No necesita broker adicional ni comparte memoria de cola con los límites de autenticación. Esta decisión reduce las piezas operativas para la carga actual; se evaluará Celery si aparecen necesidades de enrutamiento, paralelismo o integraciones que justifiquen sus costos. No se atribuyen a esta cola garantías sobre efectos externos que todavía no ejecuta.

Usar eventos/tareas persistentes en PostgreSQL para efectos que no deban perderse. Un dispatcher publica después de commit; worker con contexto de tenant explícito, deduplicación durable, reintentos limitados/backoff, timeout y registro de intentos. Una outbox no da “exactly once” por sí sola: requiere efectos idempotentes y recuperación de estados intermedios. No guardar la única copia del trabajo en Redis.

Separar Redis de autenticación de la cola cuando la evaluación de recursos/persistencia lo justifique. El frontend podrá habilitar opciones disponibles, consultar próximas/últimas ejecuciones, errores y notificaciones; ningún editor visual complejo en esta primera versión. Correos deshabilitados o backend controlado durante pruebas; activar destinatarios reales exige autorización.

## Operaciones e integraciones: decisiones previas

La instrucción posterior del usuario permite continuar sin cortes por entrega; las decisiones comerciales o reglas financieras sin definir siguen necesitando una especificación concreta. Debe definir compra, recepción, obligación y pago; si habrá entrega parcial, reservas, stock negativo permitido y depósitos múltiples. Partir de un almacén simple si los casos no justifican varios. Una factura no descontará stock automáticamente sin regla aprobada. No presentar el sistema como contabilidad de partida doble.

La Entrega 5 diseña credenciales por empresa, scopes y servicios de negocio compartidos. Webhooks requieren firma, ventana/replay, claves rotables, validación/resolución de destinos y bloqueo de redes internas/metadatos para SSRF, además de límites y logs sin secretos. Una credencial API no debe saltarse las mismas reglas financieras ni conceder privilegios administrativos de plataforma.

La Entrega 6 es planificación comercial. Quedan pendientes precios, moneda de suscripción, proveedor, pruebas gratuitas, límites, exportación, retención, impago, suspensión/reactivación y soporte. Separar entitlements comerciales de roles. No activar cobros, proveedores reales, correos masivos ni restricciones nuevas sin aprobación específica.

## Pruebas y aceptación transversal

Para cada ruta, tarea, archivo y notificación nueva, probar: anónimo; usuario sin membresía; tenant inactivo; rol insuficiente; autorizado; tenant ajeno; mezcla de identificadores; membresía desactivada. Añadir usuario desactivado, expiración/reutilización de tokens y carreras cuando corresponda. Mantener 401/403/404 según contrato existente sin revelar recursos externos.

Cada entrega debe incluir servicio real, persistencia, validación backend, UI conectada, estados de carga/vacío/error, auditoría pertinente, documentación y pruebas de regresión. Un botón, enum o endpoint vacío no satisface la aceptación.

Después de cada bloque:

1. Tests específicos y suite backend pertinente en PostgreSQL real; `TransactionTestCase` para bloqueos/carreras, rollback e integridad Decimal.
2. Ruff/formato, Django checks, migraciones pendientes y OpenAPI sin warnings. Nunca rebajar el umbral de cobertura del 85 %; la línea base medida es 91 % redondeado.
3. ESLint, generación de tipos + TypeScript, build, auditorías de dependencias separando producción/desarrollo y E2E relevantes.
4. Navegador desktop/tablet/mobile, teclado, contraste, movimiento reducido y captura de excepciones/5xx. No declarar accesibilidad completa solo por Axe.
5. Revisar diff y compatibilidad de API; migraciones aditivas primero y estrategia para históricos. Ninguna migración destructiva sin autorización.
6. Completar comprobaciones de infraestructura en el stack objetivo PG17/Redis8/Node22 antes de declarar preparación operativa. No trasladar resultados de PG18 o caché local como prueba del target.

Actualizar `ENTERPRISE_AUDIT.md`, este roadmap y, cuando comiencen cambios de código, `ENTERPRISE_ARCHITECTURE.md`, `ENTERPRISE_TESTING.md` y `ENTERPRISE_CHANGELOG.md` según contenido real. Mantener coherencia con TESTING/OPERATIONS/README existentes. Al cerrar cada entrega informar funcionalidades verificadas/implementadas, paths, migraciones, dependencias, pruebas aprobadas/fallidas/omitidas, cobertura, riesgos, seguridad, impacto y siguiente paso.

## Autorización registrada

La aprobación inicial fue recibida y posteriormente ampliada al desarrollo continuo local, sin pausas por entrega. Las alertas de dependencias sin solución compatible y las pruebas que requieran infraestructura no disponible conservarán su estado explícito; no se eliminarán controles para forzar resultados.

La aprobación de este bloque autoriza el desarrollo incremental local y sus pruebas seguras. No autoriza publicación, despliegue, migraciones destructivas, servicios externos pagos, comunicaciones reales ni decisiones comerciales pendientes.

La aprobación ya fue recibida. El desarrollo continúa según la instrucción posterior del propietario, sin pausas por agrupación de trabajo. El detalle actualizado de cambios y comprobaciones se registra en `ENTERPRISE_CHANGELOG.md` y `ENTERPRISE_TESTING.md`.

## Estado del desarrollo continuo — 2026-10-15

Implementados localmente: configuración y equipo, vencimientos/cartera, analítica, ocho informes y exportaciones privadas, cola durable y notificaciones internas, proveedores, inventario, gastos/pagos, compras/recepciones, sesiones de cuenta y cambio de contraseña. Las compras se integran dentro de `operations/`, sin crear aplicaciones separadas innecesarias. Ver criterios y límites en ARCHITECTURE y resultados reales en TESTING.

Comercialización e integraciones tienen diseño en `SAAS_PRODUCT_POLICY.md`; no son módulos ejecutables por existir ese documento. La verificación de correo es optativa y está implementada con enlace firmado; MFA TOTP opcional ya está implementado y probado, incluido Django Admin. SMTP/Redis/Caddy/Compose, PostgreSQL 17 y Node 22 requieren su entorno real; la verificación local usa PostgreSQL 18.6 y Node 24. No se activan precios, restricciones o conexiones externas sin decisiones concretas.

## Cinco capacidades empresariales: estado comprobable

| Capacidad | Implementación local y evidencia | Límite pendiente |
| --- | --- | --- |
| Centralización | Empresa activa común a clientes, catálogo, comprobantes internos, cobros, equipo, configuración, proveedores, stock, gastos y compras. Servicios explícitos y relaciones históricas; tests multiempresa. | Contabilidad de partida doble y autorización fiscal no se implementan ni se simulan. |
| Automatización | Cola PostgreSQL, informes programados, avisos internos, registros de intentos, deduplicación, timeout y recuperación de concesiones; pruebas con proceso real. | Recordatorios por correo a clientes y outbox para efectos externos no están activos. Verificación/invitación usan transporte con timeout y reenvío manual. |
| Escalabilidad y personalización | Preferencias por empresa, fechas por zona, paginación, índices, reportes limitados, worker independiente y lectura analítica consistente. | Sin benchmark de producción, Redis/Compose nuevos sin ejecutar localmente; operaciones críticas se serializan por empresa. Límites de archivos/datasets son explícitos, no escalabilidad infinita. |
| Seguridad y trazabilidad | Roles verificados en Django, locks y constraints, idempotencia, auditoría transaccional, sesiones, correo verificable, Admin limitado y pruebas de abuso local. | MFA obligatorio por política todavía no se impone; políticas de retención y soporte/recuperación necesitan definición. ASVS es referencia, no certificación externa. |
| Análisis y reportes | Datos PostgreSQL reales, Decimal por moneda, cobros revertidos excluidos, períodos, aging y ocho CSV/XLSX/PDF; archivos privados con caducidad. | No cierre financiero histórico ni consolidación/convertidor de monedas. Reportes síncronos 1.000 filas; jobs 10.000 filas y 20 MiB. |
