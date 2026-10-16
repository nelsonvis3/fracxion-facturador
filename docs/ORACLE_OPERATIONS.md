# Operación de la demo Oracle

Estado: instrucciones preparadas, servidor aún no disponible. Bash remoto.

Acceso: `ssh -F /dev/null -o IdentitiesOnly=yes -i /ruta/privada/clave ubuntu@IP_CONFIRMADA`, comprobando huella y
CIDR administrativo. No publicar claves privadas. Los comandos Docker se ejecutan
con el usuario autorizado; si requiere sudo, conservar esos privilegios limitados.

En el checkout autorizado:

```bash
export COMPOSE_PROJECT_NAME=fracxion-demo
export COMPOSE_FILE=compose.yaml:compose.oracle.yaml
docker compose ps
docker compose logs --tail 100 backend worker frontend proxy
docker stats --no-stream
df -h .
docker compose exec -T backend python manage.py migrate --check
docker compose exec -T worker python manage.py job_worker_health
```

No compartir logs sin revisar datos. Docker usa rotación local acotada. La aplicación
emite JSON con ID de solicitud y campos permitidos; no registra cuerpos ni secretos.
No se habilitan access logs detallados con query strings sensibles por defecto.
Revisar journald y fijar retención según espacio/política; no conservar PII indefinidamente.

Reiniciar un servicio: `docker compose restart NOMBRE` después de investigar su
salud/logs. No reiniciar PostgreSQL para ocultar un fallo ni borrar volúmenes.
Si worker cae, API continúa y los jobs quedan en PostgreSQL; al recuperar se revisan
leases, intentos y heartbeat. Scheduler está integrado en run_jobs. Redis caído
hace que readiness falle; recuperar límites compartidos sin reemplazarlos por caché
local de producción. Docker restart no reinicia automáticamente un contenedor solo
por estar unhealthy: los healthchecks requieren observación y respuesta operativa.

Monitoreo ligero propuesto: sondeo externo /health y /ready cada 5 min, certificado
semanal, `docker stats`, disco y fecha de último backup; revisar worker/jobs fallidos.
No se contrató ni activó un proveedor de monitoreo. Antes de G definir quién recibe
alertas y cómo. Umbrales candidatos: disco 80 %, RAM sostenida 85 %, /ready fallida
dos veces y backup >26 h. Medir y ajustar en la VM; no son resultados de carga.

## Actualización manual protegida

Desarrollar/pruebas locales → revisar diff/secretos → commit candidato → autorización
C/push → verificar CI de ese commit → backup externo probado → construir imágenes
secuencialmente → migraciones revisadas → actualizar servicios → smoke/E2E públicos.
No hay despliegue automático conectado a push. El workflow CI actual no accede a OCI.

Conservar SHA previo y digests de imágenes antes de actualizar. No efectuar pull
sobre cambios locales en el servidor. Preparar un checkout de release o avance
fast-forward autorizado y verificar estado; no usar reset --hard sobre trabajo ajeno.
Durante builds de actualización observar memoria y pausar worker si fuera necesario,
registrando la pausa y recuperando después sus jobs.

Rollback: si esquema es compatible, recuperar imagen/release anterior y probarlo.
No revertir migraciones a ciegas. Si requiere restaurar datos, detener escrituras,
respaldar estado actual y aprobar restauración en otra base/volumen; reconciliar
cambios posteriores al backup. Nunca `docker compose down -v`.

Backup: `systemctl start fracxion-backup.service` y
`journalctl -u fracxion-backup.service --since today`, solamente tras instalar y
probar el backend externo. Restauración: ORACLE_BACKUP_RECOVERY.md.
