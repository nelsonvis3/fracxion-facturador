# Fracxion: Netlify + Render + Neon

Configuración preparada para una demo con tráfico bajo. No representa un despliegue
real ni una garantía de disponibilidad. Oracle queda descartado para este camino.

## Servicios y límites

| Servicio | Plan elegido | Responsabilidad |
| --- | --- | --- |
| Netlify | Free | Next.js y proxy de API/admin bajo el mismo origen |
| Render Web Service | Free | Django y un proceso `run_jobs`, compartiendo 512 MB |
| Render Key Value | Free | Redis para los límites de intentos; red privada |
| Neon PostgreSQL | Free | Datos y resultados de trabajos durables |
| Brevo | Free | Correos transaccionales por API HTTPS |

No se crea PostgreSQL en Render: su plan gratuito vence a los 30 días. Neon tiene
cuotas de almacenamiento, cómputo y transferencia; el worker hace consultas
periódicas mientras está activo, por lo que también consume cómputo de Neon.
Render puede suspender un servicio gratuito con tráfico saliente inusualmente alto.

Render suspende el servicio después de 15 minutos sin tráfico. La primera visita
puede tardar alrededor de un minuto en despertarlo. El proxy devuelve 503 si no
obtiene respuesta a tiempo; no reenvía automáticamente una operación de escritura.
Los trabajos quedan en PostgreSQL y se retoman cuando el servicio vuelve. Las
automatizaciones no tienen ejecución puntual durante la suspensión.

Redis Free pierde su contenido al reiniciar: se reinician los contadores de límite
de intentos, pero las sesiones y los trabajos permanecen en PostgreSQL. No usar el
disco efímero de Render para datos. Los reportes de esta aplicación se guardan en
PostgreSQL; revisar las cuotas cuando se generen archivos grandes.

Mantener todos los recursos en Free, sin mejoras automáticas ni planes de prueba
pagos. En Netlify Free el sitio se pausa al agotar la cuota; los deploys también
consumen créditos. Las condiciones deben revisarse en el panel antes de crear cada
recurso. Esta configuración no mantiene el backend despierto mediante pings.

## Archivos

- [`render.yaml`](../render.yaml): un servicio web y un Key Value, ambos `plan: free`.
- [`netlify.toml`](../netlify.toml): build del frontend y rutas del proxy.
- [`deploy/render/.env.example`](../deploy/render/.env.example): referencia de variables.
- [`backend/render_start.py`](../backend/render_start.py): migra, recopila estáticos y
  supervisa Gunicorn y el worker. Si uno termina, detiene el otro y devuelve error.
- [`backend/config/render_settings.py`](../backend/config/render_settings.py): perfil
  de producción separado del despliegue Docker/Caddy existente.

## Conectar cuentas

1. Conectar las integraciones de **Render** y **Neon** para poder crear recursos y
   consultar su estado. Usar las cuentas del propietario del proyecto.
2. Crear o iniciar sesión en **Netlify** con acceso al repositorio
   `nelsonvis3/fracxion-facturador`. Confirmar el plan Free.
3. Crear una cuenta **Brevo Free**, validar un remitente y habilitar correo
   transaccional. La aprobación de la cuenta y la entrega deben comprobarse con un
   correo real. Un remitente gratuito puede ser reescrito por Brevo; un dominio
   propio autenticado mejora la entrega, pero no se compra un dominio en este plan.

Las credenciales se cargan directamente en las variables de los proveedores o en
un archivo local ignorado con permisos 600. No pegarlas en el chat, commits, logs,
capturas ni variables `NEXT_PUBLIC_*`.

## Orden del despliegue

1. Revisar las pruebas y publicar en GitHub el commit que se vaya a desplegar.
   Los cambios locales sin push no están disponibles para Render/Netlify.
2. Crear el proyecto de Neon en Free, **PostgreSQL 17**, y en la región más cercana
   a Render Virginia (US East). Guardar la URL **pooled** con TLS y su URL directa
   para backups. `DATABASE_URL` acepta `sslmode` y `channel_binding`; conserva las
   contraseñas escapadas. Las conexiones persistentes y los cursores de servidor
   están desactivados para funcionar con el pool transaccional.
3. Crear el proyecto Netlify desde el repositorio. Usar `netlify.toml`: base
   `frontend`, comando `npm run build -- --webpack`, publicación `.next`. Confirmar
   el subdominio real asignado. Aún no anunciar la aplicación: falta conectar API.
4. Crear el Blueprint de Render desde `render.yaml`. Revisar que **solo** cree
   `fracxion-api` y `fracxion-cache`, ambos Free, en la misma región. El despliegue
   automático queda desactivado: las migraciones se aplican al iniciar y deben
   revisarse antes de cada actualización.
5. Completar las variables solicitadas:

   | Variable | Valor |
   | --- | --- |
   | `DJANGO_SECRET_KEY` | Secreto aleatorio de al menos 50 caracteres |
   | `MFA_ENCRYPTION_KEYS` | Clave Fernet válida, persistente; no rotar sin conservar la anterior |
   | `DATABASE_URL` | URL pooled de Neon con TLS |
   | `CORS_ALLOWED_ORIGINS` | `https://` + dominio real de Netlify |
   | `CSRF_TRUSTED_ORIGINS` | El mismo origen exacto, sin `/` final |
   | `FRONTEND_PASSWORD_RESET_URL` | Ese origen + `/reset-password` |
   | `BREVO_API_KEY` | Clave de API transaccional, no clave SMTP |
   | `DEFAULT_FROM_EMAIL` | `Fracxion <remitente-verificado>` |

   Render genera `FRACXION_PROXY_SECRET`; el mismo valor se configura en Netlify.
   `REDIS_URL` se obtiene del Key Value por red interna. El host permitido se
   obtiene de `RENDER_EXTERNAL_HOSTNAME`. No usar `*`.

6. En Netlify, agregar **solo al contexto de producción**, con alcance Functions:

   - `BACKEND_ORIGIN`: la URL HTTPS real de Render, sin ruta, consulta ni credenciales.
   - `FRACXION_PROXY_SECRET`: exactamente el secreto generado en Render.

   Mantener `NEXT_PUBLIC_API_BASE_URL` vacío. Volver a desplegar Netlify después de
   configurar las variables: las Edge Functions necesitan un nuevo deploy para
   incorporarlas. No dar credenciales de producción a Deploy Previews.
7. Comprobar la lista de aceptación de abajo antes de anunciar la URL pública.

Para crear los dos secretos manuales sin imprimirlos en la terminal, ejecutar desde
la raíz (no reemplaza un archivo existente):

```bash
backend/.venv/bin/python tools/create-hosting-secrets.py
```

El archivo `.env.hosting-secrets` queda ignorado por Git con permisos 600. Copiar los
valores directamente a los paneles y guardar una copia privada: perder las claves
MFA impide descifrar los factores ya configurados.

## Cookies, CSRF y proxy

El navegador usa `/api/` en el dominio de Netlify. La Edge Function reenvía cookies,
CSRF y el cuerpo por HTTPS a Render, agregando un secreto privado y la IP que
Netlify proporciona mediante `context.ip`. Nunca confía en cabeceras de IP del
visitante. Django verifica ese secreto antes de aceptar la IP y el esquema HTTPS.

Las rutas de admin y sus archivos estáticos pasan por el mismo proxy. El acceso
directo al host de Render se rechaza salvo `/health/` y `/ready/`, que usa el
proveedor. Las cookies siguen siendo HttpOnly, Secure, host-only y SameSite=Lax.
Las respuestas del proxy no se cachean; no se siguen redirects con el secreto.

El perfil Render requiere el proxy: no publicar su URL como API para el navegador.
En local siguen funcionando los ajustes originales de desarrollo y Docker/Caddy.

## Aceptación en los proveedores

- Backend saludable y migraciones completas; verificar también que el worker siga activo.
- Frontend compilado por el adaptador de Netlify y rutas `/api/`, `/admin/`, `/static/` funcionales.
- Registro, login, logout y recarga conservan la sesión con cookies del dominio Netlify.
- Un POST sin CSRF se rechaza y el acceso directo a Render no permite falsificar IP.
- Crear empresa, cliente, producto, documento interno y pago; comprobar aislamiento.
- Pedir una exportación y descargarla; medir memoria de API + worker + exportador
  dentro de 512 MB. La preparación local no prueba este límite real.
- Solicitar verificación/recuperación por correo y abrir el enlace recibido.
- Repetir el acceso tras una suspensión real y comprobar recuperación de trabajos.
- Revisar cuotas y realizar un backup con la URL directa de Neon, más una restauración
  en una base distinta. El backup/restic de Oracle no se ejecuta en este alojamiento.

## Fuentes oficiales

- [Render Free: suspensión, SMTP, almacenamiento y cuotas](https://render.com/docs/free)
- [Blueprints de Render](https://render.com/docs/blueprint-spec)
- [Neon: precios y cuotas](https://neon.com/pricing)
- [Netlify: Next.js](https://docs.netlify.com/build/frameworks/framework-setup-guides/nextjs/overview/)
- [Netlify: variables de Edge Functions](https://docs.netlify.com/build/edge-functions/environment-variables/)
- [Netlify: planes](https://www.netlify.com/pricing/)
- [Brevo: envío transaccional](https://developers.brevo.com/reference/send-transac-email)

## Validación local de esta preparación — 22 de octubre de 2026

- Suite completa: **381 tests correctos**, con PostgreSQL **18.6** temporal en UTF-8.
  Luego se agregó un caso de sesión/CSRF a través del proxy y pasaron los **18 tests
  focalizados** de hosting y configuración de seguridad. El destino propuesto usa
  PostgreSQL 17; su ejecución real sigue pendiente.
- Proxy Netlify: **5 pruebas** de cookies, cuerpo, cabeceras falsificadas, redirects,
  fallo de red y respuesta HTML de arranque. Son pruebas locales con fetch simulado,
  no una ejecución de Edge Functions en Netlify.
- Supervisor: **2 pruebas con procesos reales**, ante fallo del hijo y SIGTERM.
- `render.yaml` validado con el esquema JSON oficial de Render; TOML y rutas locales
  de Netlify comprobados.
- Ruff, lint frontend, TypeScript y build webpack de producción correctos.
- Next.js y eslint-config-next actualizados a **16.4.2** por los avisos de seguridad
  de 16.4.0. La instalación actualizada informó **0 vulnerabilidades** en npm.
- No se construyó la imagen Docker en esta máquina (Docker no está instalado).
  No hay recursos provisionados, URL pública, prueba del límite de 512 MB, correo
  real ni validación de navegador contra los proveedores. Todo ello requiere las
  cuentas conectadas y completar la aceptación del despliegue.

Las comprobaciones HTTP de sesión usan el cliente de tests de Django con CSRF
activado; no se presentan como una prueba de navegador. Los cambios están locales,
sin commit ni push realizados por esta preparación.
