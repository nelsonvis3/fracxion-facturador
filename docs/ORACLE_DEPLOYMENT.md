# Despliegue reproducible en una VM Oracle

Estado: procedimiento preparado; no ejecutado en OCI. Todos los bloques de
servidor se ejecutan con **Bash**. Desde Fish se puede abrir una sesión SSH y
seguir en Bash remoto; no copiar asignaciones Bash como si fueran Fish.

## Acceso y Ubuntu

Después de aprobar A/B, comprobar la huella SSH por un canal de confianza y
conectar `ssh -F /dev/null -o IdentitiesOnly=yes -i /ruta/privada/clave ubuntu@IP_CONFIRMADA`. La clave privada
permanece fuera del repositorio. `-F /dev/null` evita el archivo global de SSH
que actualmente tiene permisos inválidos en CachyOS; no desactiva verificación
de host ni cambia archivos del sistema. La prueba local `ssh -G` pasó sin conectar.
Verificar la huella antes de aceptar el servidor y usar después un archivo SSH
privado específico si se desean aliases/proxy. Clonar el repositorio público por
HTTPS evita depender de la autenticación SSH de Git durante la instalación. Verificar `uname -m`, `/etc/os-release`, `free -m`,
`df -h`, `timedatectl`, conectividad y rutas. Aplicar actualizaciones de seguridad
con una ventana de reinicio si hace falta. Mantener una segunda conexión SSH
antes de tocar reglas de red; no cambiar autenticación SSH sin probar acceso.

Instalar Engine, CLI, containerd, Buildx y Compose Plugin mediante el
[repositorio APT oficial de Docker para Ubuntu](https://docs.docker.com/engine/install/ubuntu/),
con su keyring firmado y el codename/arquitectura reales. La guía admite ARM64.
No usar convenience scripts desconocidos ni añadir usuarios innecesarios al grupo
docker: su acceso equivale a privilegios elevados. Verificar servicio habilitado,
`docker version`, `docker compose version`, `docker buildx version` y un contenedor
oficial. Registrar las versiones instaladas, no suponer que son las locales.

Preparar `/srv/fracxion` para el checkout autorizado y `/etc/fracxion` privado.
Recuperar el commit aprobado por C desde GitHub o un artefacto revisado; confirmar
HEAD y árbol limpio. Crear `.env` privado modo 600; ver ORACLE_ENVIRONMENT.md.
No copiar bases de datos ni `.env` de desarrollo al servidor.

## Antes de arrancar

1. Confirmar cuentas/recursos/costos, imagen ARM y dominio seleccionados.
2. Comparar subred Docker 172.29.33.0/24 con VCN y otras redes Docker. Si hay
   conflicto, revisar conjuntamente subnet/IP del proxy y TRUSTED_PROXY_NETWORKS.
3. Ejecutar `FRACXION_ROOT=/srv/fracxion bash deploy/oracle/preflight.sh`.
4. Registrar HEAD en `release-commit.txt`, hashes de lockfiles e imágenes resueltas.
5. En instalación existente, backup externo y prueba de lectura antes de migrar.
   Inspeccionar `migrate --plan` y SQL de migraciones nuevas; cualquier operación
   destructiva requiere aprobación F. La nueva accounts 0004 solo crea una tabla.

En `/srv/fracxion`, Bash:

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

El último check conserva su umbral: con HSTS limitado al host se esperan W005 y
W021. Revisar y registrar esa decisión con el dominio real antes de la apertura;
no bajar el umbral, silenciar avisos o activar preload solo para lograr verde.
No continuar si aparecen otros fallos.

Antes de iniciar proxy, definir el acceso demo, obtener aprobación G y configurar
DNS mediante D. El servidor puede validarse previamente con un túnel SSH y hosts
autorizados, manteniendo el acceso público restringido. Solo tras esos controles:

```bash
docker compose up -d backend worker frontend
docker compose up -d proxy
docker compose ps
```

No ejecutar `down -v`, reset de bases ni prune global. El worker incluye scheduler;
no crear Celery/Beat adicionales. Verificar cada healthcheck, logs y uso de recursos.

## Dominio, HTTPS y SMTP

Elegir un dominio/subdominio controlado por el propietario. Si no existe, evaluar
un nombre gratuito ofrecido por un proveedor confiable o uno basado en la IP,
explicando disponibilidad, privacidad y continuidad; no se eligió ninguno ni se
supone control de `example.invalid`. No comprar dominios.

Opciones investigadas si no hay dominio propio:

| Opción | Uso y limitaciones |
| --- | --- |
| Subdominio de dominio propio | Preferido para portfolio si existe: nombre estable y control DNS, pendiente de titularidad/selección. |
| [Duck DNS](https://www.duckdns.org/) | DNS dinámico gratuito; requiere cuenta y elegir un nombre disponible. Su token se guarda privado. La app sigue alojada enteramente en OCI. |
| [sslip.io / nip.io](https://nip.io/) | DNS con IP incorporada, sin crear un dominio propio. Admite certificado público HTTP-01/Caddy; depende del servicio y de límites de emisión compartidos. La URL cambia si cambia la IP y es menos adecuada para una referencia permanente. |

No se registró ningún nombre ni se publicó ninguna IP. Esperar la elección del propietario. El DNS externo no distribuye los servicios de la aplicación entre proveedores.

Tras D, A apunta a la IPv4 confirmada; eliminar AAAA obsoleto solo con revisión.
Validar desde resolvedores externos. Caddy obtiene/renueva certificados con
[HTTPS automático](https://caddyserver.com/docs/automatic-https); conservar su
volumen de datos. Comprobar redirección, certificado y recursos sin contenido mixto.

Elegir SMTP existente/autorizado y probar TLS en 587 desde la VM. No depender del
puerto 25 ni suponer que OCI Email Delivery está habilitado para una cuenta gratis.
Verificar cuotas de envío, remitente/SPF/DKIM y una cuenta sintética autorizada.
Mailtrap sandbox acredita captura, no entrega a usuarios. Sin proveedor probado,
SMTP y los flujos dependientes siguen pendientes; no fingir entrega correcta.

Aplicar ORACLE_DEPLOYMENT_TESTING.md y guardar evidencias del dominio real antes
de enlazar la demo desde portfolio/GitHub/LinkedIn.
