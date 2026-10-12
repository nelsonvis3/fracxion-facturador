import os
import secrets
import subprocess
import sys

from django.test import SimpleTestCase


class ProductionSecurityTests(SimpleTestCase):
    def load_production_settings(self, overrides=None):
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
            [sys.executable, "-c", "import config.settings"],
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

    def test_https_proxy_requires_explicit_valid_networks(self):
        for networks in ["", "not-a-network"]:
            with self.subTest(networks=networks):
                result = self.load_production_settings(
                    {"TRUST_PROXY_HTTPS": "True", "TRUSTED_PROXY_NETWORKS": networks}
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ImproperlyConfigured", result.stderr)
