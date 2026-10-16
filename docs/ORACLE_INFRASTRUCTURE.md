# Infraestructura OCI propuesta

Estado: diseño local, pendiente de aprobación A. No se creó ningún recurso.

| Recurso | Configuración candidata | Verificación pendiente |
| --- | --- | --- |
| VM | `fracxion-demo`, VM.Standard.A1.Flex, ARM64, 2 OCPU, 12 GB | Región principal, cuota libre, capacidad del AD, etiqueta elegible. |
| Imagen | Ubuntu Server 24.04 LTS ARM64, imagen OCI elegible | OCID y etiqueta Always Free en la consola. |
| Boot | 50 GB, rendimiento base elegible | Volúmenes existentes y total combinado de la cuenta. |
| Red | Una VCN/subred pública, Internet Gateway y ruta 0.0.0.0/0 | Reutilizar solamente si está autorizado y no altera otros sistemas. |
| IP | Una IPv4 pública de la VM | Disponibilidad, tipo/precio vigente en la cuenta; no asumir reserva gratuita. |
| NSG | 80/443 TCP, 443 UDP para HTTP/3, 22 TCP desde IP administrativa | CIDR administrativo y reglas heredadas de security lists. |
| Backups | Bucket privado OCI Object Storage, misma región | Cuota libre real, tamaño/retención y aprobación; no se creó. |

[Oracle Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
publica actualmente 1.500 OCPU-h y 9.000 GB-h/mes para A1, equivalentes a
2 OCPU/12 GB, y 200 GB combinados de boot/block en la región principal.
Son límites de cuenta compartidos, no una asignación libre confirmada para esta VM.
Los límites de Object Storage dependen del estado de la suscripción: revisar la
cuenta antes de seleccionar bucket, tier o retención. No usar créditos temporales
como prueba de costo recurrente cero.

No se contrata balanceador, NAT Gateway, base administrada, Kubernetes ni otra VM.
No cambiar a Pay As You Go ni aceptar una estimación con recursos de pago.
Ante advertencia de precio/cuota/elegibilidad, detenerse. Ante falta de capacidad,
revisar otro AD elegible de la misma región, un intento acotado por opción y luego
esperar una decisión; no confundir falta de hosts con falta de cuota.

## Presupuesto de recursos (estimación, no benchmark)

El overlay fija máximos: PostgreSQL 2 GiB; Redis 256 MiB; API 1,5 GiB;
worker 1,5 GiB; frontend 1 GiB; Caddy 256 MiB. Suman 6,5 GiB; no son consumo
medido ni memoria reservada. Los límites CPU se comparten entre servicios y
pueden sumar más que las 2 OCPU; el host sigue teniendo 2 OCPU. Gunicorn empieza
con dos workers y el procesador de tareas con un trabajo simultáneo.

Los 50 GB son una propuesta inicial para demo: SO/Docker ~8 GB, imágenes/build
~10 GB, datos sintéticos inicialmente pequeños y reserva operativa. No se ha medido
el build ARM64. Verificar espacio antes/después; no iniciar build con menos de
15 GB libres ni llenado superior al 80 %. Construir servicios secuencialmente y
observar RAM; si el build no cabe, ajustar el proceso o consultar una alternativa
sin crear automáticamente una VM mayor. No borrar volúmenes para ganar espacio.

Las mediciones locales (~314 MiB backend con venv, ~577 MiB node_modules y
artefactos frontend de cientos de MiB) no equivalen al tamaño final de imágenes.
Los logs Docker rotan a 10 MiB × 3 por servicio con driver local, más overhead.

## Riesgo de recuperación de instancias

Oracle puede recuperar instancias gratuitas consideradas inactivas tras un
período de siete días con bajo uso de CPU/red y, en A1, memoria. No crear carga
artificial. Mantener copia cifrada fuera de la VM, clave de recuperación fuera de
OCI y procedimiento ORACLE_BACKUP_RECOVERY.md. Una IP efímera puede cambiar al
recrear la VM: el DNS se actualiza solo con autorización D.
