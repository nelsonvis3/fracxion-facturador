"""Validate production Django controls with disposable values, never real secrets/mail."""

import os
import secrets
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet

backend = Path(__file__).resolve().parents[1] / "backend"
env = {
    **os.environ,
    "DJANGO_ENV": "production",
    "DJANGO_DEBUG": "False",
    "DJANGO_SETTINGS_MODULE": "config.settings",
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
    "MFA_ENCRYPTION_KEYS": Fernet.generate_key().decode(),
    "DJANGO_ALLOWED_HOSTS": "demo.example.invalid",
    "REDIS_URL": "redis://127.0.0.1:6379/1",
    "FRONTEND_PASSWORD_RESET_URL": "https://demo.example.invalid/reset-password",
    "DJANGO_EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    "EMAIL_HOST": "smtp.example.invalid",
    "TRUST_PROXY_HTTPS": "True",
    "TRUSTED_PROXY_NETWORKS": "172.29.33.10/32",
    "CSRF_TRUSTED_ORIGINS": "https://demo.example.invalid",
    "SECURE_HSTS_INCLUDE_SUBDOMAINS": "False",
    "SECURE_HSTS_PRELOAD": "False",
    "SECURE_SSL_REDIRECT": "True",
    "SESSION_COOKIE_SECURE": "True",
    "CSRF_COOKIE_SECURE": "True",
}
raise SystemExit(
    subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=backend,
        env=env,
        check=False,
    ).returncode
)
