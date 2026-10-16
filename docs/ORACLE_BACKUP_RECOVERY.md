# Copias cifradas y recuperación

Estado: backup/restauración local cifrada comprobados con datos sintéticos;
almacenamiento externo y automatización en OCI pendientes de A/B.

## Qué respalda

PostgreSQL incluye usuarios, empresas, finanzas, auditoría, cola durable, logos,
adjuntos y reportes binarios. Respaldar además `.env`, commit/lockfiles/configuración
aprobada y datos Caddy. Redis solo mantiene límites de autenticación: reiniciarlo
pierde temporalmente sus contadores; no pierde operaciones financieras ni jobs.
No restaurar solamente Redis ni considerarlo fuente de tareas.

Propuesta: Restic cifrado hacia bucket privado OCI S3 compatible, fuera de la VM.
La aplicación completa sigue en una sola VM; el bucket es una copia, no una base
remota. Requiere cuota/costo confirmados y aprobación de recurso. Usar credenciales
mínimas de bucket y conservar contraseña Restic fuera de OCI.
Referencias: [Restic](https://restic.readthedocs.io/en/stable/040_backup.html) y
[API S3 compatible OCI](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/s3compatibleapi.htm).

`deploy/oracle/backup.sh` prepara tres snapshots etiquetados: base, configuración y
TLS. El dump se produce mediante `--stdin-from-command`, que rechaza fallos de
pg_dump; no deja dump legible temporal en el servidor. Comprueba el índice del dump
y `restic check`. La cuenta del servicio necesita Docker y es privilegiada: no
se concede a otros usuarios. Instalar Restic oficial verificando firma/checksum.

Después de crear/autenticar el repositorio externo y restaurar una copia de prueba:
instalar el servicio/timer provistos bajo /etc/systemd/system, archivo de entorno
privado y directorio /var/lib/fracxion. Validar `systemd-analyze verify`, ejecutar una
vez, comprobar logs/objeto externo y solo entonces habilitar el timer. Hora propuesta:
03:30 UTC con dispersión 15 min y recuperación tras apagado (`Persistent=true`).

Objetivo inicial propuesto: RPO 24 h; RTO por medir en reconstrucción real. Retención
candidata 7 diarias + 4 semanales + 3 mensuales, condicionada al tamaño/cuota de la
cuenta. Revisar primero `restic forget --dry-run` con tags/host correctos. No instalar
prune automático antes de aprobación: eliminar snapshots también es destructivo.
Limitar crecimiento por monitoreo; no contar deduplicación como ahorro garantizado.

## Restauración aislada

Seleccionar snapshot **completo** con tags/host y fecha conocidos, no cualquier
`latest` de otro tipo. Ejecutar `restic check --read-data` periódicamente y extraer
el dump con permisos 600. Validar `pg_restore --list` antes de restaurar.
Crear una base NUEVA de pruebas, con PostgreSQL 17 y sin correo externo. Restaurar
con `--no-owner --single-transaction --exit-on-error`; comprobar migraciones,
conteos, saldos, reversiones, stock, archivos y MFA. No usar `--clean` contra la
base activa ni restaurar un dump PostgreSQL 18 en PostgreSQL 17. La prueba local
utilizó PostgreSQL 18.6 en ambos lados; la de producción debe usar 17 en ambos.

## Pérdida de VM / reconstrucción

1. Aprobar VM nueva elegible, preparar Ubuntu/Docker/red sin reutilizar disco ajeno.
2. Recuperar commit aprobado y lockfiles; construir ARM64 y confirmar digests.
3. Recuperar secretos mediante gestor seguro: SECRET_KEY y claves MFA originales
   para descifrar semillas; contraseña Restic y acceso externo fuera del host perdido.
4. Recuperar base y datos Caddy en volúmenes NUEVOS. No arrancar app/worker sobre
   la base vacía ni ejecutar migraciones contra una restauración incompleta.
5. Restaurar dump PostgreSQL 17, revisar `migrate --plan`, luego migraciones aditivas.
6. Revisar trabajos pendientes antes de iniciar worker; respetar leases/idempotencia.
7. Invalidar sesiones restauradas con un procedimiento aprobado si la pérdida del
   host implica exposición; no asumir que respaldar sesiones equivale a revocarlas.
8. Actualizar A/AAAA mediante D si cambió IP; verificar DNS/HTTPS y URL pública.
9. Repetir pruebas funcionales de ORACLE_DEPLOYMENT_TESTING y medir RTO.

La prueba local actual restauró saldos, reversiones, compras, stock y sesiones con
MFA activo desde repositorio Restic cifrado e integridad completa. Esa prueba no
acredita todavía recuperación desde un bucket OCI ni continuidad ante caída de OCI.
