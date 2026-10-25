import json
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from config.database import database_from_url
from config.email_backend import BrevoEmailBackend, EmailDeliveryError
from config.render_proxy import NetlifyProxyMiddleware


class DatabaseURLTests(SimpleTestCase):
    def test_neon_url_preserves_escaped_credentials_and_tls(self):
        config = database_from_url(
            "postgresql://user:p%40ss%2Fword@db.example/db%20name?sslmode=require&channel_binding=require"
        )
        self.assertEqual(config["PASSWORD"], "p@ss/word")
        self.assertEqual(config["NAME"], "db name")
        self.assertEqual(config["OPTIONS"]["channel_binding"], "require")
        self.assertTrue(config["DISABLE_SERVER_SIDE_CURSORS"])
        self.assertEqual(config["CONN_MAX_AGE"], 0)

    def test_invalid_and_insecure_urls_do_not_leak_credentials(self):
        for value in [
            "sqlite:///tmp/db",
            "postgresql://user:private-value@host/db?sslmode=disable",
            "postgresql://user:private-value@host:bad/db",
            "postgresql://host/db",
            "postgresql://user:private-value@host/db?options=unsafe",
            "postgresql://user:private-value@host/db?sslmode=require&sslmode=disable",
        ]:
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured) as error:
                database_from_url(value)
            self.assertNotIn("private-value", str(error.exception))


@override_settings(BREVO_API_KEY="synthetic-api-key", EMAIL_TIMEOUT=10)
class BrevoTransportTests(SimpleTestCase):
    def message(self):
        return EmailMultiAlternatives(
            "Verificá tu correo",
            "Enlace privado",
            "Fracxion <from@example.com>",
            ["to@example.com"],
        )

    @patch("config.email_backend.urlopen")
    def test_acceptance_preserves_payload_and_uses_https(self, send):
        send.return_value.__enter__.return_value.status = 201
        message = self.message()
        message.attach_alternative("<p>Enlace privado</p>", "text/html")
        self.assertEqual(BrevoEmailBackend().send_messages([message]), 1)
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.brevo.com/v3/smtp/email")
        payload = json.loads(request.data)
        self.assertEqual(payload["sender"], {"name": "Fracxion", "email": "from@example.com"})
        self.assertEqual(payload["textContent"], "Enlace privado")
        self.assertEqual(payload["htmlContent"], "<p>Enlace privado</p>")
        self.assertEqual(send.call_args.kwargs["timeout"], 10)

    @patch("config.email_backend.urlopen")
    def test_provider_error_does_not_leak_body_or_retry(self, send):
        send.side_effect = HTTPError(
            "https://api.brevo.com", 429, "private body", {}, BytesIO(b"token")
        )
        with self.assertRaises(EmailDeliveryError) as error:
            BrevoEmailBackend().send_messages([self.message()])
        self.assertEqual(str(error.exception), "El proveedor rechazó el correo (HTTP 429).")
        send.assert_called_once()

    @patch("config.email_backend.urlopen", side_effect=URLError("private data"))
    def test_fail_silently_and_connection_failures(self, send):
        self.assertEqual(BrevoEmailBackend(fail_silently=True).send_messages([self.message()]), 0)
        with self.assertRaises(EmailDeliveryError) as error:
            BrevoEmailBackend().send_messages([self.message()])
        self.assertNotIn("private data", str(error.exception))

    @patch("config.email_backend.urlopen")
    def test_unsupported_attachment_is_not_silently_discarded(self, send):
        message = self.message()
        message.attach("a.txt", "private", "text/plain")
        with self.assertRaises(EmailDeliveryError):
            BrevoEmailBackend().send_messages([message])
        send.assert_not_called()

    @patch("config.email_backend.urlopen")
    def test_no_recipients_sends_nothing(self, send):
        self.assertEqual(BrevoEmailBackend().send_messages([EmailMessage("Subject", "Body")]), 0)
        send.assert_not_called()


@override_settings(
    FRACXION_PROXY_SECRET="synthetic-proxy-secret-at-least-32-characters",
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
)
class NetlifyProxyTests(SimpleTestCase):
    def request(self, **kwargs):
        return RequestFactory().post("/api/auth/login/", REMOTE_ADDR="10.0.0.1", **kwargs)

    def test_direct_request_cannot_spoof_scheme_or_ip(self):
        downstream = MagicMock(return_value=HttpResponse())
        request = self.request(
            HTTP_X_FORWARDED_PROTO="https", HTTP_X_FRACXION_CLIENT_IP="203.0.113.2"
        )
        self.assertEqual(NetlifyProxyMiddleware(downstream)(request).status_code, 403)
        self.assertFalse(request.is_secure())
        downstream.assert_not_called()

    def test_authenticated_proxy_sets_ip_and_secure_scheme(self):
        request = self.request(
            HTTP_X_FRACXION_PROXY_SECRET="synthetic-proxy-secret-at-least-32-characters",
            HTTP_X_FRACXION_CLIENT_IP="203.0.113.2",
        )
        response = NetlifyProxyMiddleware(lambda request: HttpResponse())(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(request.is_secure())
        self.assertEqual(request.META["REMOTE_ADDR"], "203.0.113.2")
        self.assertNotIn("HTTP_X_FRACXION_PROXY_SECRET", request.META)

    def test_invalid_proxy_ip_rejected(self):
        request = self.request(
            HTTP_X_FRACXION_PROXY_SECRET="synthetic-proxy-secret-at-least-32-characters",
            HTTP_X_FRACXION_CLIENT_IP="invalid",
        )
        self.assertEqual(
            NetlifyProxyMiddleware(lambda request: HttpResponse())(request).status_code, 400
        )

    def test_health_checks_need_no_secret_but_post_cannot_bypass(self):
        handler = NetlifyProxyMiddleware(lambda request: HttpResponse())
        self.assertEqual(handler(RequestFactory().get("/ready/")).status_code, 200)
        self.assertEqual(handler(RequestFactory().post("/ready/")).status_code, 403)


class RenderSessionFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        secret = "synthetic-proxy-secret-at-least-32-characters"
        self.enterContext(
            self.settings(
                MIDDLEWARE=[
                    "config.render_proxy.NetlifyProxyMiddleware"
                    if item == "config.middleware.TrustedProxyMiddleware"
                    else item
                    for item in settings.MIDDLEWARE
                ],
                ALLOWED_HOSTS=["api.example"],
                CSRF_TRUSTED_ORIGINS=["https://site.example"],
                FRACXION_PROXY_SECRET=secret,
                SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
                SECURE_SSL_REDIRECT=True,
                SESSION_COOKIE_SECURE=True,
                CSRF_COOKIE_SECURE=True,
            )
        )
        get_user_model().objects.create_user(
            email="hosting@example.com", password="SyntheticTestOnly123!"
        )
        self.client = Client(
            enforce_csrf_checks=True,
            HTTP_HOST="api.example",
            HTTP_ORIGIN="https://site.example",
            HTTP_X_FRACXION_PROXY_SECRET=secret,
            HTTP_X_FRACXION_CLIENT_IP="203.0.113.8",
        )

    def test_session_and_csrf_survive_the_authenticated_proxy(self):
        csrf = self.client.get("/api/auth/csrf/")
        self.assertEqual(csrf.status_code, 200)
        payload = {"email": "hosting@example.com", "password": "SyntheticTestOnly123!"}
        rejected = self.client.post("/api/auth/login/", payload, content_type="application/json")
        self.assertEqual(rejected.status_code, 403)
        login = self.client.post(
            "/api/auth/login/",
            payload,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )
        self.assertEqual(login.status_code, 200, login.content)
        for name in ("sessionid", "csrftoken"):
            cookie = self.client.cookies[name]
            self.assertTrue(cookie["secure"])
            self.assertTrue(cookie["httponly"])
            self.assertEqual(cookie["domain"], "")
            self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)
        self.assertEqual(
            self.client.get("/api/auth/me/", HTTP_X_FRACXION_PROXY_SECRET="forged").status_code, 403
        )
        token = self.client.cookies["csrftoken"].value
        self.assertEqual(
            self.client.post(
                "/api/auth/logout/", HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://attacker.example"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=token).status_code, 200
        )
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
