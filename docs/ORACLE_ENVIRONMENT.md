# Variables de producción Oracle

No hay secretos reales en este documento. `.env.example` es la referencia base;
`.env` definitivo vive solo en el servidor con modo 600, fuera de Git.

| Variable | Uso y validación |
| --- | --- |
| SITE_DOMAIN | Host controlado, sin esquema/ruta. Fija hosts, CSRF y enlaces del mismo origen. |
| DJANGO_SECRET_KEY | Aleatoria, al menos 50 caracteres; no ejemplos/desarrollo. |
| MFA_ENCRYPTION_KEYS | Clave Fernet dedicada; lista por comas, nueva primero. Guardar fuera de la VM. |
| POSTGRES_PASSWORD | Secreto aleatorio exclusivo de esta demo. |
| DEFAULT_FROM_EMAIL | Remitente autorizado por SMTP. |
| EMAIL_HOST / EMAIL_PORT | Servidor real autorizado; STARTTLS 587 propuesto. |
| EMAIL_USE_TLS | True con el proveedor STARTTLS; no desactivar para resolver fallos. |
| EMAIL_HOST_USER / EMAIL_HOST_PASSWORD | Credenciales privadas del proveedor. |

Generar secretos directamente en el servidor o mediante un gestor seguro y
escribirlos sin mostrarlos en chat, historial o logs. Para Fernet puede usarse
`Fernet.generate_key()` desde un contenedor backend ya construido; redirigir la
salida a un archivo privado, no a una captura pública. No reutilizar la clave
sintética pública de E2E. Una clave de cifrado inválida hace fallar el arranque.
La pérdida de todas las claves vuelve irrecuperables las semillas MFA cifradas.
Rotación: mantener claves previas para lectura hasta ejecutar/probar un proceso
explícito de recifrado; quitar una clave del entorno no recifra registros existentes.

Compose establece production, DEBUG=False, DB interna sin TLS dentro de la VM,
Redis db1, hosts/orígenes HTTPS, proxy exacto, SMTP y recuperación mismo origen.
El overlay fija dos workers web y HSTS sin subdominios/preload. Las cookies son
HttpOnly y Secure. Conexiones internas sin TLS requieren que esos puertos nunca
se publiquen; no trasladar esta configuración a una red entre máquinas.

Frontend: NEXT_PUBLIC_API_BASE_URL vacío durante el build Docker. No contiene
secretos y no necesita otro dominio/CORS. Variables NEXT_PUBLIC se fijan al
compilar; cambiar solo `.env` no reescribe un bundle ya generado.

Backups: `/etc/fracxion/backup.env`, modo 600, con FRACXION_ROOT, RESTIC_REPOSITORY,
RESTIC_PASSWORD_FILE y las credenciales restringidas requeridas por el backend.
Para S3 compatible OCI, configurar endpoint/namespace/región/bucket reales,
AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY del mecanismo autorizado. No confundir
estas credenciales con la clave SSH ni copiarlas al `.env` del backend. Conservar
la contraseña Restic y accesos de recuperación en un gestor fuera de esta VM.

## Contrato de MFA

Las cuentas sin MFA conservan la respuesta de login existente. Para una cuenta
que lo activa, POST /api/auth/login/ devuelve `mfa_required: true`, `expires_in: 300`
y CSRF sin autenticar. El cliente completa POST /api/auth/mfa/login/ con `code`;
solo entonces recibe user y una sesión autenticada. No se acepta enviar el
segundo factor en parámetros URL. Los clientes anteriores deben incorporar ese
estado antes de habilitar MFA en sus cuentas.

GET /api/auth/mfa/ muestra disponibilidad, activación y cantidad de códigos.
POST a la misma ruta con current_password inicia un alta de diez minutos.
POST /api/auth/mfa/manage/ con action confirm/disable/recovery, current_password
y code confirma, desactiva o renueva recuperación. La semilla y los nuevos códigos
solo se muestran durante su generación; no se pueden consultar nuevamente.
Django Admin solicita el factor en su formulario cuando la cuenta tiene MFA.
