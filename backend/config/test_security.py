import os
import secrets
import subprocess
import sys

from cryptography.fernet import Fernet
from django.test import SimpleTestCase


class ProductionSecurityTests(SimpleTestCase):
    def load_production_settings(self, overrides=None, module="config.settings"):
        env = {
            **os.environ,
            "DJANGO_ENV": "production",
            "DJANGO_DEBUG": "False",
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
            "DJANGO_ALLOWED_HOSTS": "audit.example",
            "DB_NAME": "postgres",
            "DB_USER": "postgres",
            "DB_PASSWORD": "synthetic-test-only",
            "REDIS_URL": "redis://127.0.0.1:6379/1",
            "FRONTEND_PASSWORD_RESET_URL": "https://audit.example/reset-password",
            "DJANGO_EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "EMAIL_HOST": "smtp.example",
            "SESSION_COOKIE_SECURE": "True",
            "CSRF_COOKIE_SECURE": "True",
            "SECURE_SSL_REDIRECT": "True",
            "TRUST_PROXY_HTTPS": "False",
            **(overrides or {}),
        }
        return subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_secure_production_configuration_loads(self):
        result = self.load_production_settings()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_rejects_insecure_cookies_and_http(self):
        for flag in ["SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT"]:
            with self.subTest(flag=flag):
                result = self.load_production_settings({flag: "False"})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ImproperlyConfigured", result.stderr)

    def test_production_accepts_https_mail_and_requires_key(self):
        values = {
            "DJANGO_EMAIL_BACKEND": "config.email_backend.BrevoEmailBackend",
            "BREVO_API_KEY": "synthetic-key",
            "EMAIL_HOST": "",
        }
        result = self.load_production_settings(values)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.load_production_settings({**values, "BREVO_API_KEY": ""})
        self.assertNotEqual(result.returncode, 0)

    def test_console_mail_remains_forbidden_in_production(self):
        result = self.load_production_settings(
            {"DJANGO_EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend"}
        )
        self.assertNotEqual(result.returncode, 0)

    def test_render_requires_production_mfa_and_proxy_secret(self):
        values = {
            "MFA_ENCRYPTION_KEYS": Fernet.generate_key().decode(),
            "FRACXION_PROXY_SECRET": secrets.token_urlsafe(32),
        }
        result = self.load_production_settings(values, "config.render_settings")
        self.assertEqual(result.returncode, 0, result.stderr)
        for override in [
            {"DJANGO_ENV": "development"},
            {"MFA_ENCRYPTION_KEYS": ""},
            {"FRACXION_PROXY_SECRET": ""},
        ]:
            with self.subTest(override=override):
                result = self.load_production_settings(
                    {**values, **override}, "config.render_settings"
                )
                self.assertNotEqual(result.returncode, 0)

    def test_https_proxy_requires_explicit_valid_networks(self):
        for networks in ["", "not-a-network"]:
            with self.subTest(networks=networks):
                result = self.load_production_settings(
                    {"TRUST_PROXY_HTTPS": "True", "TRUSTED_PROXY_NETWORKS": networks}
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ImproperlyConfigured", result.stderr)
