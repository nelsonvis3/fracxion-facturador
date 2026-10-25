# Desarrollo local

Los pasos cortos están en el [README](../README.md#cómo-correrlo). Acá están las variables, los comandos de administración y qué revisar cuando algo no arranca.

## Variables del backend (`backend/.env`)

El archivo se crea desde [`backend/.env.example`](../backend/.env.example).

| Variables | Uso |
| --- | --- |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_SSLMODE` | Conexión a PostgreSQL. El ejemplo usa la base `facturador` en `127.0.0.1:5432` |
| `DJANGO_ENV`, `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` | Entorno, modo debug, clave y hosts aceptados |
| `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` | Orígenes desde los que entra el frontend |
| `FRONTEND_PASSWORD_RESET_URL` | Formulario de recuperación. En desarrollo, `http://localhost:3000/reset-password` |
| `DJANGO_EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL` | Correo. El ejemplo imprime los mensajes en la terminal de Django |
| `REDIS_URL` | Límites de intentos compartidos. Opcional en desarrollo, obligatorio en producción |

El frontend lee `NEXT_PUBLIC_API_BASE_URL` de `frontend/.env.local`, creado desde [`frontend/.env.example`](../frontend/.env.example). La variable se fija al compilar: si cambia, hay que volver a hacer el build.

## Crear una empresa desde la terminal

Además del registro en la pantalla de login, desde `backend/`:

```bash
.venv/bin/python manage.py create_workspace \
  --email propietario@example.com \
  --name "Mi empresa" \
  --slug mi-empresa
```

Pide la contraseña sin mostrarla y puede usar una cuenta activa que ya exista. No da permisos de plataforma: para entrar a `http://localhost:8000/admin/` hace falta una cuenta aparte creada con `createsuperuser`.

## Worker de tareas

Los informes programados y los recordatorios de las automatizaciones se ejecutan fuera de la API, con:

```bash
.venv/bin/python manage.py run_jobs
```

## Build de producción local

Desde `frontend/`:

```bash
npm run build
env PORT=3000 HOSTNAME=localhost npm run start
```

`prebuild` prepara los recursos de la intro del login y `postbuild` arma la salida standalone que usa `npm run start`.

## Si algo no arranca

| Síntoma | Qué revisar |
| --- | --- |
| Django no conecta a la base | Que PostgreSQL esté corriendo y que nombre, usuario, contraseña y puerto coincidan con `backend/.env` |
| La sesión no se conserva o aparece un error CSRF | Usar el mismo hostname en los dos servicios: mezclar `localhost` y `127.0.0.1` deja las cookies en otro host |
| No llega el correo de recuperación | En desarrollo el mensaje sale en la terminal de Django |
| El frontend consulta una API vieja | Volver a compilar después de cambiar `NEXT_PUBLIC_API_BASE_URL` |
