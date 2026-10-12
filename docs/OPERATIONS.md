# Operación y despliegue

La referencia de despliegue es `compose.yaml`: un dominio HTTPS, Caddy, Next.js standalone, Gunicorn, PostgreSQL y Redis. Solo el proxy publica puertos. El backend valida sesión, CSRF, membresía y empresa activa en cada petición.

## Publicar una instalación nueva

1. Preparar un host con Docker Engine y Compose; apuntar el DNS del dominio al host y habilitar 80/443 para Caddy.
2. Copiar `.env.example` a `.env`. Configurar dominio, correo SMTP y contraseñas propias. Generar `DJANGO_SECRET_KEY` con `python -c 'import secrets; print(secrets.token_urlsafe(64))'` y guardarla solo en el entorno privado.
3. Construir y aplicar migraciones antes de iniciar la aplicación:

```sh
docker compose build
docker compose up -d database cache
docker compose run --rm backend python manage.py migrate --noinput
docker compose run --rm backend python manage.py check --deploy --fail-level WARNING
docker compose up -d
```

El propietario puede registrarse desde **Crear cuenta** en el login. `/register` crea una cuenta normal, una empresa nueva y la membresía de propietario, y abre su sesión. Como alternativa de bootstrap administrativo, usar `docker compose run --rm backend python manage.py create_workspace --email propietario@tuempresa.com --name "Tu empresa" --slug tu-empresa`; solicita una contraseña validada y puede vincular una cuenta activa existente. Ningún flujo convierte al propietario en administrador de la plataforma. Para gestionar otras cuentas, empresas y membresías desde `/admin/`, crear por separado un superusuario con `docker compose run --rm backend python manage.py createsuperuser`.

El registro público tiene CSRF, límite compartido de diez intentos por IP cada quince minutos, validación de contraseña, confirmación y unicidad de correo. No admite elegir rol ni unirse a una empresa existente. No envía un correo de verificación; SMTP continúa destinado a recuperación de acceso. Si la instalación incorpora invitaciones o verificación de correo en el futuro, implementar sus tokens y políticas como flujos separados.

`backend/start.sh` rechaza migraciones pendientes, recolecta estáticos y ejecuta Gunicorn. El frontend incluye su servidor standalone y los assets. El código no incorpora usuarios de demo en producción.

```sh
curl --fail https://tu-dominio.com/health/
curl --fail https://tu-dominio.com/ready/
docker compose ps
docker compose logs --tail=100 backend frontend proxy
```

`/health/` comprueba que el proceso responde. `/ready/` consulta PostgreSQL y escribe/lee Redis; devuelve 503 sin detalles internos si una dependencia falla. La existencia de tablas y la consistencia de migraciones se verifican al arrancar, antes de atender tráfico.

## HTTPS, cookies e IP del cliente

Producción requiere `DJANGO_ENV=production`, `DEBUG=False`, hosts explícitos, clave aleatoria de al menos 50 caracteres, Redis y SMTP. Cookies de sesión y CSRF son HttpOnly y Secure. El frontend obtiene el token CSRF enmascarado por JSON y utiliza cookies de sesión; no almacena tokens de acceso en localStorage.

El arranque de producción también rechaza `SESSION_COOKIE_SECURE=False`, `CSRF_COOKIE_SECURE=False` y `SECURE_SSL_REDIRECT=False`. Si `TRUST_PROXY_HTTPS=True`, requiere `TRUSTED_PROXY_NETWORKS` con redes válidas explícitas. Estos controles no convierten una configuración de desarrollo en una instalación de producción segura.

La topología provista usa un solo dominio: `/api/`, `/admin/` y `/static/` van a Django; las páginas van a Next.js. `NEXT_PUBLIC_API_BASE_URL` queda vacío durante el build Docker. Para hosting separado, definir la URL pública antes de compilar y configurar CORS/CSRF con orígenes explícitos. Dominios de sitios diferentes requieren revisar SameSite y las restricciones del navegador sobre cookies de terceros; la instalación de referencia evita esa dependencia.

Caddy ocupa `172.29.33.10` en la red privada y reemplaza `X-Client-IP` con la dirección observada. Django acepta esa cabecera únicamente desde `TRUSTED_PROXY_NETWORKS`; descarta `X-Forwarded-Proto` de emisores no autorizados. Esto evita que usuarios falsifiquen la IP para eludir límites. Si se cambia el proxy o la red, actualizar ambos extremos; si se añade un CDN, configurar explícitamente los proxies de confianza del borde.

HSTS se activa por un año e incluye subdominios. Caddy lo entrega en todas las rutas, incluidas las páginas de Next.js; Django también lo aplica a sus respuestas HTTPS. Si se cambia la política, actualizar `deploy/Caddyfile` y los valores de Django de forma consistente para la infraestructura real. La configuración sigue los controles de la [lista de despliegue de Django](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).

## Correos

Configurar `EMAIL_HOST`, puerto, TLS, usuario, contraseña, remitente autorizado y el dominio final de recuperación. En desarrollo el backend de consola imprime el enlace; en producción se utiliza SMTP. El envío tiene timeout y registra fallos sin revelar la existencia de una cuenta al solicitante.

La entrega a bandeja de entrada debe comprobarse con el proveedor final: solicitar recuperación, abrir el enlace HTTPS, cambiar la contraseña e intentar reutilizar el enlace. Las pruebas automatizadas verifican el mensaje y el cambio con un backend de correo de pruebas; no prueban entregabilidad real ni DNS del remitente.

## Backups y restauración

Los datos persisten en `postgres_data`. Crear copias cifradas fuera del host y definir retención, responsables y una frecuencia acordada. Un volumen Docker no sustituye un backup.

```sh
mkdir -p backups
docker compose exec -T database pg_dump -U facturador -d facturador -Fc > backups/facturador.dump
```

Restaurar primero en una base nueva de un entorno separado. Ejemplo para una base vacía `facturador_restore`, creada por el administrador de PostgreSQL:

```sh
docker compose exec -T database pg_restore -U facturador -d facturador_restore --no-owner < backups/facturador.dump
```

Comprobar cantidades de empresas, clientes, facturas y pagos, saldos y una muestra del historial antes de promover esa base. Conservar la imagen de aplicación que corresponde al esquema restaurado. Redis almacena límites temporales, no datos contables ni sesiones.

## Actualizaciones

- Ejecutar CI, revisar migraciones y generar un backup verificable antes de actualizar.
- Construir imágenes y aplicar migraciones como un paso de release. La migración `billing.0003` amplía precisión y agrega snapshots; no cambia precios ni reescribe documentos históricos.
- Desplegar y verificar `/ready/`, registro de una cuenta de prueba con su empresa, login, creación de borrador y un flujo de consulta.
- Una reversión del código debe ser compatible con el esquema presente. No revertir migraciones automáticamente sobre datos de producción.
- Programar `python manage.py clearsessions` para eliminar sesiones vencidas y vigilar espacio de PostgreSQL, errores, latencia y fallos de correo.

## Alcance operativo

Se construyeron las imágenes con sus dependencias reales y se verificó el arranque en un stack local aislado. Se comprobaron HTTPS local, páginas/assets, estáticos de Django, disponibilidad de PostgreSQL/Redis, login/logout, CSRF y cookies de producción. Dominio público, emisión de certificados públicos, SMTP real, backups externos y aceptación con usuarios reales se completan en la infraestructura de destino.

El limitador usa Redis y operaciones atómicas, con ventana de 15 minutos. Si Redis falla, la autenticación no continúa sin controles; `/ready/` indica la indisponibilidad. Los límites no reemplazan las defensas del proxy ni el monitoreo de abuso.
