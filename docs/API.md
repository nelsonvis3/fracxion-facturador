# Contrato de la API

Con una sesión iniciada, el esquema OpenAPI completo está en `/api/schema/` y la documentación navegable en `/api/docs/`. Este documento resume las rutas y las reglas comunes.

## Reglas comunes

- Todas las rutas terminan en `/`.
- Los recursos de una empresa usan UUID y viven bajo `/api/tenants/{tenant_id}/`.
- Las listas se paginan de a 25 y devuelven `count`, `next`, `previous` y `results`.
- Los importes viajan como texto (`"121.00"`) para no perder decimales.
- Las escrituras necesitan las cookies de sesión y el header `X-CSRFToken`. El token se pide en `/api/auth/csrf/` antes de cada escritura, porque rota.
- Respuestas de error: `401` sin sesión, `403` sin permiso para la operación, `404` si el objeto es de otra empresa, `400` por validación y `429` por límite de intentos.

## Cuenta y sesión

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/api/auth/csrf/` | Obtener `csrfToken` y su cookie |
| POST | `/api/auth/register/` | Crear cuenta y empresa propia (`first_name`, `last_name` opcional, `company_name`, `email`, `password`, `password_confirm`) |
| POST | `/api/auth/login/` | Abrir sesión con `email` y `password` |
| POST | `/api/auth/mfa/login/` | Completar el login con el código TOTP o un código de recuperación |
| POST | `/api/auth/logout/` | Cerrar la sesión |
| GET | `/api/auth/me/` | Datos de la cuenta |
| GET | `/api/auth/tenants/` | Empresas de la cuenta y rol en cada una |
| GET, POST | `/api/auth/mfa/`, `/api/auth/mfa/manage/` | Estado, alta y baja de MFA |
| POST | `/api/auth/password/change/` | Cambiar la contraseña |
| POST | `/api/auth/password-reset/`, `/api/auth/password-reset/confirm/` | Recuperar el acceso por correo |
| GET, POST | `/api/auth/email-verification/`, `.../request/`, `.../confirm/` | Verificar el correo |
| POST | `/api/auth/invitations/preview/`, `/api/auth/invitations/accept/` | Ver y aceptar una invitación |
| GET, POST | `/api/auth/sessions/`, `.../{id}/revoke/`, `.../revoke-others/` | Ver y cerrar sesiones abiertas |
| GET | `/api/reference/countries/`, `/api/reference/countries/{code}/subdivisions/` | Países y provincias para los formularios |

## Operaciones por empresa

Todas las rutas empiezan con `/api/tenants/{tenant_id}/`.

| Módulo | Rutas |
| --- | --- |
| Clientes | `customers/`, `customers/{id}/`, `customers/{id}/deactivate/` |
| Productos y servicios | `products/`, `products/{id}/`, `products/{id}/deactivate/` |
| Facturas internas | `invoices/`, `invoices/{id}/`, `invoices/{id}/issue/` |
| Cobros | `payments/`, `payments/{id}/`, `payments/{id}/reverse/` |
| Proveedores | `suppliers/`, `suppliers/{id}/` |
| Inventario | `inventory/items/`, `inventory/items/{id}/`, `inventory/movements/`, `inventory/movements/{id}/`, `inventory/movements/{id}/reverse/` |
| Compras | `purchases/`, `purchases/{id}/`, `.../lines/`, `.../confirm/`, `.../receipts/`, `.../close/`, `purchase-receipts/{id}/reverse/` |
| Gastos | `expenses/`, `expenses/{id}/`, `.../post/`, `.../void/`, `.../payments/`, `.../attachment/`, `expenses/categories/`, `expense-payments/{id}/reverse/` |
| Analítica | `analytics/overview/`, `analytics/records/` |
| Informes | `reports/export/`, `reports/jobs/`, `reports/jobs/{id}/`, `.../download/`, `.../retry/` |
| Automatizaciones | `automation/rules/`, `automation/rules/{id}/`, `notifications/`, `notifications/{id}/read/` |
| Equipo y configuración | `members/`, `members/{id}/`, `invitations/`, `.../resend/`, `.../revoke/`, `settings/`, `settings/logo/` |
| Auditoría | `audit-events/`, `audit-events/{id}/` |

Clientes y productos se reactivan con `PATCH` y `{"is_active": true}`.

## Ejemplos

Un borrador se crea con producto y cantidad. El servidor busca precio e impuesto en el catálogo de la empresa y calcula los totales; el cuerpo no lleva importes:

```json
{
  "customer": "00000000-0000-4000-8000-000000000010",
  "currency": "ARS",
  "lines": [
    { "product": "00000000-0000-4000-8000-000000000020", "quantity": "2.500" }
  ],
  "notes": "Condiciones comerciales"
}
```

Un cobro sobre una factura emitida:

```json
{
  "invoice": "00000000-0000-4000-8000-000000000030",
  "method": "bank_transfer",
  "amount": "40.00",
  "external_reference": "TRANSFERENCIA-DE-EJEMPLO"
}
```

Los métodos de cobro son `cash`, `bank_transfer`, `debit_card`, `credit_card`, `digital_wallet`, `check` y `other`. Los UUID de los ejemplos son ilustrativos.

## Permisos de los módulos comerciales

| Operación | `owner` | `admin` | `accountant` | `sales` | `viewer` |
| --- | :---: | :---: | :---: | :---: | :---: |
| Consultar clientes, catálogo, facturas y cobros | Sí | Sí | Sí | Sí | Sí |
| Crear o editar clientes y catálogo | Sí | Sí | No | No | No |
| Crear borradores y emitir facturas | Sí | Sí | No | No | No |
| Registrar cobros | Sí | Sí | Sí | No | No |
| Revertir cobros | Sí | Sí | No | No | No |
| Consultar auditoría | Sí | Sí | No | No | No |

La política general está en [`tenancy/permissions.py`](../backend/tenancy/permissions.py): todos los roles leen y solo `owner` y `admin` escriben, salvo las excepciones que declara cada vista (por ejemplo, `accountant` puede registrar cobros en [`billing/views.py`](../backend/billing/views.py)).
