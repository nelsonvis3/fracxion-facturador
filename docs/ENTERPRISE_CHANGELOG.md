# Desarrollo empresarial continuo

Baseline: `60753dc`. Trabajo local autorizado el 2026-10-14; ampliado por el propietario a revisión y mejora continua del proyecto, sin pausas por entregas. No hay publicación o despliegue autorizado. El informe de auditoría inicial conserva su valor como baseline, no como descripción del estado implementado actual.

## Continuación del 15 de octubre

- Verificación explícita de correo: enlace firmado de un uso, nonce rotatorio, vencimiento 24 h, límites por cuenta/IP, CSRF también anónimo, aislamiento entre cuentas y estado invalidado si cambia la dirección. UI y buzón de pruebas; sin bloqueos nuevos ni correos automáticos.
- Admin conserva versiones de sesión y nonces actuales al guardar formularios cargados antes de cambios de seguridad; contraseña Admin actualiza solo el hash bajo lock de cuenta.

- Pedidos de compra, líneas, recepciones parciales, reversiones completas, cierre/cancelación y vínculo opcional desde gastos. UI funcional y permisos backend; stock y pagos separados. Migración aditiva `operations/0003_purchaseorder_purchaseline_expense_purchase_order_and_more.py`, aplicada únicamente en QA. Ninguna dependencia nueva.
- Filtros UUID en cobros, inventario y gastos/compras para evitar distinguir existencia global de identificadores ajenos. Reproducción fallida y prueba de regresión conservadas.
- Recuperación de contraseña con enlaces nuevos por fragmento; compatibilidad con enlaces anteriores por query y verificación de ausencia de token en la navegación HTTP. Separación visual de enlaces de la pantalla de verificación.
- Identificadores inválidos o inexistentes en contraseña Admin devuelven 404, sin 500 ni auditoría falsa de cambio.
- Logs estructurados con correlación UUID generada por servidor y pruebas de omisión de argumentos/mensajes sensibles.
- Prueba de backup/restauración con comparación financiera exacta entre bases sintéticas independientes. Diseño comercial y de integraciones en `SAAS_PRODUCT_POLICY.md`, sin activar restricciones o cobros.

## Implementación en curso

- Servicios explícitos para cambios de membresía y protección del último propietario, incluidos cambios desde Django Admin y desactivación de cuentas. Bloqueos de cuenta antes de empresa y pruebas de carreras; no se permite eliminar cuentas/membresías/empresas desde Admin.
- Auditoría de cambios administrativos, grupos/permisos y contraseñas administrativas; eventos mínimos de login/logout/reset/denegación sin registrar credenciales ni tokens. Denegaciones acotadas por ventana; límites específicos para Admin y para cuentas entre distintas IP.
- Emisión con comprobación agrupada de productos, manteniendo cálculos y transacción. Prueba de consultas constante entre una y cien líneas.
- Typecheck con `next typegen`, contraste de textos secundarios de Clientes y restauración de foco en modales.
- Configuración por empresa con país, zona, moneda predeterminada, contacto, plazos y pie. Logos PNG/JPEG limitados, decodificados y recodificados con Pillow; almacenamiento privado en PostgreSQL, acceso autenticado por tenant.
- Invitaciones con token aleatorio de uso único, hash persistido, vencimiento de siete días, revocación, rotación al reenviar, correo después de commit y resultado de entrega. Aceptación de cuenta existente exige identidad destinataria; cuenta nueva no crea una empresa extra ni privilegios de plataforma.
- Vencimientos opcionales, plazos y snapshots del emisor/pie en borradores nuevos. Sin datos inventados para documentos históricos ni cambios en emitidas. Filtros de cartera sobre saldos efectivos y zona de la empresa.
- Claves opcionales `Idempotency-Key` para cobros: restricción por tenant, huella de contenido, repetición del mismo resultado y conflicto 409 para otro contenido. Solicitudes sin clave conservan la semántica anterior. Formulario conectado y contrato de headers documentado en OpenAPI.
- Analítica por moneda/período con datos reales, comparación, antigüedad, clientes/productos y medios de cobro. Snapshots PostgreSQL coherentes ante un cobro concurrente; sin multiplicación de totales por joins.
- Ocho informes CSV/XLSX/PDF: ventas, cobros, cartera, movimientos de cliente, productos, resumen interno, gastos y cuentas por pagar. Protección de fórmulas, importes exactos, descargas privadas y parámetros desconocidos rechazados.
- Cola durable PostgreSQL, worker separado con timeout de ocho minutos, concesiones, fencing de procesos anteriores, tres intentos, backoff e historial. Resultados limitados y con expiración; reglas por zona/frecuencia, avisos internos y latido de salud. Compose incorpora worker sin activar reglas por defecto.
- Proveedores editables/desactivables, inventario por movimientos, umbrales/avisos, ajustes y reversión. No se descuenta stock por facturar; no admite saldo negativo ni cambios de unidad que reinterpreten historia. Bloqueo de empresa antes de producto/cliente en CRUD, alineado con operaciones financieras.
- Gastos con borrador y registro inmutable, impuesto explícito, categorías, adjuntos privados PNG/JPEG recodificados, pagos parciales/totales, idempotencia, reversión y anulación con controles. La obligación, su pago y las existencias son conceptos separados.
- Seguridad de cuenta: inventario privado de sesiones, revocación individual, invalidación de otros accesos con contraseña actual y cambio de contraseña conservando el dispositivo actual. Una versión inicial cero conserva hashes Django existentes; la revocación global también invalida sesiones anteriores no inventariadas. Reset/Admin retiran accesos inventariados correspondientes. Pruebas de secretos y fallback de claves.
- E2E con API propia por archivo de pruebas, sin relajar límites de seguridad. Nuevos recorridos de configuración, invitaciones, equipo, vencimiento y teclado.

## Migraciones aditivas creadas

- `tenancy.0002_businesssettings_tenantinvitation`.
- `billing.0004_invoice_due_date_invoice_footer_snapshot_and_more`.
- `billing.0005_payment_idempotency_key_payment_request_digest_and_more`.
- `automation.0001_initial`, `automation.0002_workerheartbeat_alter_job_result_expires_at`.
- `operations.0001_initial`, `operations.0002_expensecategory_expense_expensepayment_and_more` (consultar el nombre exacto en migrations).
- `accounts.0002_user_session_version_accountsession`.
- `accounts.0003_user_email_verification_nonce_user_email_verified_at_and_more`.
- `operations.0003_purchaseorder_purchaseline_expense_purchase_order_and_more`.

Solo se aplicaron a bases nuevas de pruebas. No se alteraron migraciones anteriores ni se migró una base comercial.

## Dependencias

Producción: `Pillow==12.3.0` para imágenes, `reportlab==5.0.1` y `openpyxl==3.1.5` para archivos exportables. Desarrollo: `axe-core==4.14.0` declarado directamente para pruebas reproducibles de accesibilidad. No se hicieron actualizaciones npm forzadas. La revisión del 15 de octubre encontró cero avisos conocidos de Python y npm de producción; el advisory GHSA-vfj7-8cjw-p6xm seguía sin parche declarado en tooling de desarrollo. No confundir esa observación con garantía futura; se vuelve a consultar al cerrar la revisión.

## Estado de validación

Consultar `ENTERPRISE_TESTING.md`. Cada resultado corresponde al estado probado en ese momento; ningún resultado anterior acredita cambios posteriores automáticamente. La revisión funcional, adversarial y de interfaz continúa.
