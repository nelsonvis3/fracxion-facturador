# Diseño de comercialización e integraciones

Estado: diseño técnico y decisiones abiertas, 2026-10-15. No activa precios, cobros, límites comerciales, pasarelas o conexiones externas. La operación existente conserva su disponibilidad. Los módulos ejecutables y sus resultados están separados en `ENTERPRISE_ARCHITECTURE.md` y `ENTERPRISE_TESTING.md`.

## Suscripciones y derechos de uso

Roles y suscripciones son controles distintos. Una membresía responde qué puede hacer una persona dentro de una empresa. Una suscripción determina qué capacidades contrató esa empresa. Una API nunca debe convertir una suscripción en permiso de propietario, ni un superusuario/rol administrativo en comprobante de pago.

| Concepto propuesto | Responsabilidad |
| --- | --- |
| PlanVersion | Definición inmutable/versionada de capacidades y límites; moneda/precio solo después de decisión comercial. |
| OrganizationSubscription | Empresa, versión de plan, proveedor si lo hubiera, estado, período vigente, trial opcional, cancelación y próxima revisión. |
| FeatureEntitlement | Capacidad habilitada y límite configurable de una versión de plan. |
| UsageEvent / UsageCounter | Consumos deduplicados por efecto de negocio y período. No contar reintentos de una emisión como documentos nuevos. |
| ProviderEvent | ID único del proveedor, tipo, verificación, estado de procesamiento y resultado mínimo; sin guardar secretos ni cuerpos innecesarios. |
| SubscriptionTransition | Historia de cambios de estado, actor/origen y motivo. |

Posibles familias **sin precios o cuotas inventadas**:

| Familia | Alcance candidato | Decisión pendiente |
| --- | --- | --- |
| Gratuita | Núcleo de gestión y exportación de datos propios. | Capacidad de usuarios/documentos, soporte y costo operativo admisible. |
| Equipo | Colaboración, configuración de equipos e informes programados. | Límites y tratamiento de funciones ya disponibles en empresas existentes. |
| Negocio | Mayor capacidad y futuras integraciones autorizadas. | Necesidad real de integraciones, soporte y acuerdos operativos. |

Antes de imponer restricciones debe aprobarse una política para empresas existentes, incluida preservación de sus derechos actuales. Una migración no asignará retrospectivamente deuda ni bloqueará documentos históricos.

## Ciclo comercial propuesto

Estados posibles: trial, activa, pago pendiente, suspendida, cancelada y finalizada. Los estados exactos y períodos de gracia dependen de decisiones comerciales. Una cancelación programada al final del período no equivale a borrar la empresa. Una reactivación debe conservar identificadores y registros.

La suspensión no elimina facturas, pagos, auditoría o stock. Como criterio de diseño, deben mantenerse lectura, exportación, revisión de seguridad y contacto de soporte; cualquier restricción de nuevas escrituras requiere política aprobada. Los límites de recursos de una exportación no son cuotas de un plan comercial.

No se necesita una pasarela para modelar los derechos de uso, pero no se puede afirmar que hay facturación de suscripciones sin integrar y probar el proveedor elegido. La implementación futura debe verificar firmas, deduplicar eventos, reintentar de forma durable y reconciliar periódicamente el estado externo. Un webhook recibido no cambia saldos financieros de Fracxion eludiendo sus servicios.

Decisiones comerciales necesarias: países y monedas de venta, precios y periodicidad, impuestos aplicables al servicio, proveedor, reembolsos, trial, gracia/suspensión, exportación, retención, soporte y políticas de cancelación. Ninguno de estos valores se infiere de la moneda de las facturas internas de cada empresa.

## Administración y soporte de plataforma

El staff de plataforma sigue separado de las membresías empresariales. No se añade impersonación silenciosa ni acceso financiero por marcar `is_staff`. Cualquier futura herramienta de soporte con acceso excepcional debe identificar al operador, alcance, vigencia, razón y autorización, y dejar auditoría. Las herramientas no podrán editar directamente emitidas o borrar cobros para corregir un problema.

El panel comercial futuro administrará suscripciones y soporte; no se presenta Django Admin como un portal SaaS completo. Deben definirse contactos de soporte y responsabilidades operativas antes de ofrecer acuerdos de disponibilidad.

## API keys e integración de servicios

Propuesta: credencial aleatoria de alta entropía, identificador público y prefijo para selección; almacenar solo su huella verificable, fecha de creación, último uso, vencimiento y revocación. Nunca devolver nuevamente el secreto completo. Rotar creando otra credencial con ventana de transición limitada, sin sobrescribir silenciosamente la anterior.

Cada clave debe pertenecer a una única empresa y a un responsable activo. Scopes iniciales candidatos: lectura/escritura de clientes y catálogo, lectura/creación/emisión de documentos y registro de pagos. Los scopes financieros no se concederán por un wildcard implícito. Revocar/desactivar el responsable o su membresía debe invalidar el acceso.

La autenticación mediante clave debe tener una ruta clara y no convertir una cookie de navegador en una excepción a CSRF. Una credencial inválida responde 401; no debe caer silenciosamente en otra identidad. Después de autenticar siguen aplicándose tenant, scopes, permisos y los servicios comerciales existentes. Los eventos identificarán la credencial mediante su ID público; no guardarán el secreto.

Versionar contratos mediante evolución compatible y un namespace cuando haya una ruptura demostrada. Mantener OpenAPI y pruebas de consumidores. No activar una nueva versión solo por renombrar rutas. Los límites deben aplicarse por empresa/credencial y devolver Retry-After cuando proceda; las cuotas comerciales son una capa posterior.

## Webhooks salientes

Diseño propuesto, sin destinos externos configurados ni envíos reales:

1. Registrar un evento de dominio en PostgreSQL dentro de la transacción de negocio.
2. Generar entregas persistentes por suscripción/destino después de confirmar; unicidad por evento y destino.
3. Firmar cuerpo y timestamp con secreto por destino; documentar algoritmo, rotación y ventana de validez. El consumidor deberá deduplicar el ID del evento.
4. Ejecutar HTTP en un worker acotado, con timeout, límite de respuesta, reintentos/backoff y estado de cada intento. No tratar entrega HTTP como transacción financiera exactamente una vez.
5. Permitir revisión y reenvío explícito, conservando historia. No reenviar eventos arbitrarios con otro tenant.

Controles SSRF necesarios antes de habilitar destinos: HTTPS, rechazo de credenciales en URL, restricciones de puertos, bloqueo de loopback/private/link-local/multicast y endpoints de metadata, revisión de IPv4/IPv6 y direcciones embebidas, resolución y conexión coherentes frente a DNS rebinding, y red de salida restringida. Deshabilitar redirecciones o revalidar cada salto. Un regex de hostname por sí solo no satisface estos controles.

Los payloads deben ser versionados y mínimos. Evitar datos personales/financieros completos si basta ID y tipo de evento. Las respuestas de destinos no se registran completas; no deben introducir secretos en logs. No reutilizar la cola de autenticación Redis como única persistencia de entregas.

## Seguridad y explotación operativa

[OWASP ASVS](https://owasp.org/projects/asvs) se usa como referencia de controles y pruebas, no como certificación. La revisión actual comprueba sesiones/CSRF, autorización, aislamiento, entradas, archivos, precisión/transacciones, auditoría y dependencias. No se declara cobertura total de ASVS ni auditoría externa.

MFA y verificación de correo siguen pendientes de implementación y de pruebas completas, incluida la entrada por Django Admin y la recuperación. Activar MFA solo en el login público dejaría una vía alternativa de acceso; no se presentará ese resultado parcial como protección de cuentas privilegiadas. Los métodos de recuperación deben definirse antes de imponer obligatoriedad.

Producción requiere además medir recursos con carga representativa, probar el stack exacto del despliegue, validar SMTP y restaurar backups externos cifrados. La restauración local de una base sintética acredita el procedimiento de copia/restauración en ese entorno; no acredita recuperación ante pérdida del host de producción.

La verificación optativa de correo y la gestión de sesiones ya existen localmente y tienen evidencia en TESTING. MFA permanece pendiente de un flujo completo que cubra login API, Django Admin, recuperación y gestión segura de secretos; no se presenta un segundo paso visual como MFA terminado.
