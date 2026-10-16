# Despliegue en una VM de Oracle Cloud

Guía para publicar Fracxion en una sola VM ARM64 con Docker Compose. Todavía no se ejecutó en Oracle Cloud: es el procedimiento preparado, con los archivos que ya están en el repositorio.

## Qué se despliega

[`compose.yaml`](../compose.yaml) más el overlay [`compose.oracle.yaml`](../compose.oracle.yaml) levantan seis servicios. Solo Caddy publica puertos (80 y 443).

| Servicio | Memoria máxima en el overlay |
| --- | --- |
| `database` (PostgreSQL 17) | 2 GiB |
| `cache` (Redis) | 256 MiB |
| `backend` (Django + Gunicorn) | 1,5 GiB |
| `worker` (`run_jobs`, también programa las reglas) | 1,5 GiB |
| `frontend` (Next.js standalone) | 1 GiB |
| `proxy` (Caddy) | 256 MiB |

## Recursos sugeridos

| Recurso | Configuración |
| --- | --- |
| VM | VM.Standard.A1.Flex, ARM64, 2 OCPU y 12 GB |
| Sistema | Ubuntu Server 24.04 LTS ARM64 |
| Disco | 50 GB |
| Red | Una VCN con subred pública. Abrir 80/443 TCP, 443 UDP (HTTP/3) y 22 TCP solo desde tu IP |

Los límites del plan gratuito de Oracle cambian: revisalos en la [documentación de Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) antes de crear la VM.

## Variables de producción

El `.env` de la raíz (plantilla: [`.env.example`](../.env.example)) vive solo en el servidor, con permisos 600.

| Variable | Uso |
| --- | --- |
| `SITE_DOMAIN` | Dominio, sin esquema ni ruta. Define hosts, CSRF y links |
| `DJANGO_SECRET_KEY` | Aleatoria, de al menos 50 caracteres |
| `MFA_ENCRYPTION_KEYS` | Claves Fernet separadas por comas, la nueva primero. Si se pierden todas, las semillas MFA no se pueden descifrar |
| `POSTGRES_PASSWORD` | Contraseña aleatoria de la base |
| `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP con STARTTLS en el puerto 587 |

El frontend se compila con `NEXT_PUBLIC_API_BASE_URL` vacío, así consulta `/api/` en el mismo dominio.

## Pasos

1. Instalar Docker Engine y el plugin de Compose desde el [repositorio oficial para Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
2. Clonar el repositorio en `/srv/fracxion`, crear el `.env` y correr el chequeo previo:

   ```bash
   FRACXION_ROOT=/srv/fracxion bash deploy/oracle/preflight.sh
   ```

   Comprueba que la VM sea ARM64, que el checkout esté limpio, que exista el `.env` con permisos 600 y que la red `172.29.33.0/24` no choque con otra.

3. Construir, migrar y revisar la configuración:

   ```bash
   export COMPOSE_PROJECT_NAME=fracxion-demo
   export COMPOSE_FILE=compose.yaml:compose.oracle.yaml
   docker compose config --quiet
   docker compose build backend
   docker compose build frontend
   docker compose up -d database cache
   docker compose run --rm --no-deps backend python manage.py migrate --plan
   docker compose run --rm --no-deps backend python manage.py migrate --noinput
   docker compose run --rm --no-deps backend python manage.py check --deploy --fail-level WARNING
   ```

   Con HSTS limitado al host, `check --deploy` muestra los avisos W005 y W021. Son esperables hasta decidir `includeSubDomains` y `preload` con el dominio real.

4. Apuntar el DNS a la IP de la VM y levantar el resto:

   ```bash
   docker compose up -d backend worker frontend
   docker compose up -d proxy
   docker compose ps
   ```

Caddy obtiene y renueva el certificado solo ([HTTPS automático](https://caddyserver.com/docs/automatic-https)). Sin dominio propio sirven un subdominio de [Duck DNS](https://www.duckdns.org/) o un nombre de [nip.io](https://nip.io/), que cambia si cambia la IP.

## Operación

```bash
docker compose ps
docker compose logs --tail 100 backend worker frontend proxy
docker stats --no-stream
docker compose exec -T backend python manage.py migrate --check
docker compose exec -T worker python manage.py job_worker_health
```

- `/health/` indica que Django responde y `/ready/` que PostgreSQL y Redis funcionan.
- Si se cae el worker, la API sigue andando y los trabajos esperan en PostgreSQL.
- Si se cae Redis, `/ready/` falla y el login no sigue sin límites de intentos.
- Nunca correr `docker compose down -v`: borra los volúmenes con la base.

Para actualizar: probar en local, esperar el CI en verde, hacer backup, construir las imágenes de a una, revisar `migrate --plan`, migrar y reiniciar los servicios. No revertir migraciones a ciegas.

## Backups

[`deploy/oracle/backup.sh`](../deploy/oracle/backup.sh) hace tres snapshots cifrados con [Restic](https://restic.readthedocs.io/en/stable/040_backup.html): la base (con `pg_dump` sin dejar archivos temporales), la configuración y los datos de Caddy. El destino sugerido es un bucket privado de Object Storage por su API compatible con S3.

`fracxion-backup.service` y `fracxion-backup.timer` lo corren todos los días a las 03:30 UTC. Conviene habilitar el timer recién después de restaurar una copia de prueba.

Para restaurar: elegir un snapshot completo, revisar el dump con `pg_restore --list` y restaurarlo en una base nueva de PostgreSQL 17 con `--no-owner --single-transaction --exit-on-error`. Nunca con `--clean` sobre la base activa. Las claves `DJANGO_SECRET_KEY` y `MFA_ENCRYPTION_KEYS` originales hacen falta para que las cuentas con MFA sigan funcionando.
