# Seguridad y diseño de demo

Estado: controles locales probados; red/host/HTTPS públicos pendientes.
No se declara certificación ASVS ni ausencia absoluta de fallos.

## Red y host

Solo Caddy publica 80 TCP, 443 TCP/UDP; UDP corresponde a HTTP/3 y requiere regla
NSG si se mantiene. SSH 22 se limita a un CIDR administrativo comprobado. Revisar
tanto NSG como security lists: permisos amplios heredados también cuentan.
PostgreSQL/Redis/Gunicorn/Next/worker no tienen publicaciones host.

[Docker advierte](https://docs.docker.com/engine/network/packet-filtering-firewalls/)
que los puertos publicados interactúan con sus reglas de filtrado y UFW. El cierre
UFW por sí solo no prueba aislamiento: verificar OCI, listeners y pruebas externas.
No usar host networking ni exponer Docker API. Revisar salida DNS, HTTPS/ACME y
SMTP del proveedor aprobado. Mantener SSH probado durante todos los cambios.

Caddy reemplaza X-Client-IP; Django confía exclusivamente en 172.29.33.10/32 y
elimina cabeceras HTTPS de remitentes no autorizados. Cualquier cambio de red debe
mantener coherencia. HSTS de un año solo para el host; includeSubDomains y preload
se decidirán conociendo el dominio. Los warnings W005/W021 se conservan visibles.
Documentación API pública deshabilitada en producción; Admin sigue autenticado y
no es cuenta de demo. Considerar restricción de /admin por red como configuración
adicional aprobada, conservando MFA y permisos.

## Identidad

Sesiones Django/CSRF, límites IP/cuenta y eventos mínimos. MFA opcional TOTP cubre
API y Django Admin; secreto cifrado con clave dedicada y recuperación con hashes.
Cada paso TOTP/código de recuperación se consume bajo bloqueo; no se reutiliza.
Contraseña correcta solo crea desafío anónimo de cinco minutos. Recuperar contraseña
no borra MFA. Al activar/desactivar o renovar recuperación se invalidan otros accesos.
Sin ambos factores, usar un código guardado; si también se pierden, el operador
necesita un procedimiento excepcional de identidad aprobado. No hay endpoint de
soporte que desactive MFA sin autenticación. La demo no puede usar superusuario.

## Propuesta de acceso público (pendiente G, antes de implementar restricciones)

Propuesta inicial: cuenta **viewer**, empresa exclusivamente sintética, registro
público cerrado y sin acciones de cambio de credenciales para la cuenta compartida.
Permitir navegar, filtrar y consultar datos; mostrar que modificaciones requieren
una demostración individual autorizada. El cierre de sesión debe seguir operativo.
No publicar la contraseña hasta aprobar G y comprobar las restricciones.

Antes de habilitarlo se deben implementar y probar los controles faltantes de demo:

| Control propuesto | Prueba previa a G |
| --- | --- |
| Marcar la cuenta demo en backend sin permitir que un cliente asigne esa marca | Anónimo/no miembro/viewer/owner no alteran la marca ni crean staff. |
| Cerrar registro por entorno y reflejarlo en UI | Llamada directa al endpoint rechazada; botón coherente; registro local normal sin regresión. |
| Bloquear cambio/reset de contraseña, MFA y revocación global para cuenta compartida | Password pública no permite secuestrar la cuenta o invalidar otros visitantes. Logout propio sí funciona. |
| Roles de solo lectura | Probar writes directos en todos los módulos; descarga/exportación limitada según política aprobada. |
| Limitar abuso | Rate limit por IP y cuenta, sin bypass cambiando cabeceras; revisar concurrencia legítima. |
| Datos reiniciables | Restaurar fixture en entorno aislado; nunca borrar datos productivos automáticamente. |

No se habilitó este modo todavía: se presenta diseño y pruebas exigibles antes de
implementarlo, tal como pidió el propietario. Una cuenta viewer por sí sola no
protege sus propias opciones de seguridad. Una demo editable por visitante necesita
otro diseño de aislamiento/expiración y aprobación, no una contraseña owner compartida.

API keys/webhooks y funciones comerciales quedan sin activar; no hay conexiones
bancarias, cobros de suscripciones ni integración ARCA.
