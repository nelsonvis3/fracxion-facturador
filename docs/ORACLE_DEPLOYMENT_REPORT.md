# Estado de preparación y despliegue Oracle

Fecha: 2026-10-15. **Despliegue pendiente; no existe una URL pública verificada.**

| Área | Estado |
| --- | --- |
| Base Git inspeccionada | main / 2ad91d706d3c6f4b1b894c59b5d3b55bc95a25e6; coincide remoto. |
| Commit definitivo | Pendiente de revisión, commit y autorización C para publicación. |
| Región/cuenta/cuotas | Sin confirmar; no hay CLI/configuración OCI local. |
| VM propuesta | A1 ARM64, 2 OCPU, 12 GB, Ubuntu LTS, boot 50 GB; pendiente A. |
| Always Free / costos | Documentación consultada; elegibilidad y saldo de cuota de cuenta sin verificar. No se crearon recursos. |
| IP / dominio / HTTPS | No asignados/verificados; pendientes A/B/D/G. |
| Docker | Config Compose validada; Engine y contenedores de destino sin ejecutar. |
| Django / Next | 367 tests backend / 53 escenarios browser aprobados; build local. Sin ejecución pública. |
| PostgreSQL / Redis / worker | Pruebas PG18.6 y jobs locales; stack PG17/Redis8/ARM64 pendiente. |
| SMTP | Flujos locales con backend controlado; proveedor/entrega desde OCI pendiente. |
| Backups | Restic cifrado y restore local probados; repositorio externo/timer pendientes. |
| Seguridad demo | Diseño viewer/cuenta restringida presentado; controles específicos pendientes de elección/implementación antes de G. |

No se hizo push, no se cambió DNS, no se accedió a Oracle ni se activó una demo.
No se presentan suscripciones/API keys/webhooks como implementados. El proyecto
sigue siendo gestión empresarial con comprobantes internos; no factura fiscal ARCA.

La preparación/correcciones y evidencias están en ORACLE_DEPLOYMENT_AUDIT y
ORACLE_DEPLOYMENT_TESTING; infraestructura candidata en ORACLE_INFRASTRUCTURE.

Primer paso humano: confirmar cuenta activa y Home region en la consola OCI.
Después revisar cuotas/recursos existentes; solicitar A sobre configuración concreta.
Elegir dominio controlado, SMTP y política demo antes de las aprobaciones D/G.
La aprobación de recursos no autoriza publicar commits, DNS o abrir la demo.

Pruebas fallidas/avisos conservados: primer build y migraciones tuvieron límites
del sandbox y sus repeticiones pasaron; check deploy estricto mantiene los dos
warnings HSTS deliberados. La comprobación systemd depende de docker.service,
ausente localmente. ARM64 fue inspeccionado/instalado, no ejecutado.
No hay restore externo, DNS/HTTPS público ni SMTP real verificados.

La revisión incluyó los cambios finales del formulario Admin incompleto, el foco
de teclado MFA y actualización de sesiones. Backend: 367 aprobadas / cobertura
92 %. Browser: 53 escenarios únicos / 18 archivos en la suite completa y repetición
aprobada de los dos flujos afectados en el último build.
