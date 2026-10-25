"""Servidor local exclusivamente para los datos sintéticos de Playwright."""

from .test_settings import *  # noqa: F403

DATABASES["default"]["NAME"] = "test_facturador_e2e"  # noqa: F405
CORS_ALLOWED_ORIGINS = ["http://127.0.0.1:3010"]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
FRONTEND_PASSWORD_RESET_URL = "http://127.0.0.1:3010/reset-password"

# Public synthetic fixture only; never import these settings in production.
MFA_ENCRYPTION_KEYS = ["c3ludGhldGljLW1mYS1rZXktZm9yLWUyZS1vbmx5ISE="]
