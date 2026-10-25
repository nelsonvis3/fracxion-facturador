import json
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .password_reset import RESET_REQUEST_LIMIT

User = get_user_model()


class AuthenticationFlowTests(TestCase):
    """Pruebas HTTP de sesión, autenticación y protección CSRF."""

    def setUp(self):
        # Django no verifica CSRF automáticamente en su cliente
        # de pruebas, por eso lo habilitamos expresamente.
        self.client = Client(enforce_csrf_checks=True)

        self.user = User.objects.create_user(
            email="usuario.auth@example.com",
            password="SecureTestPassword123!",
            first_name="Usuario",
            last_name="Prueba",
        )

        self.csrf_url = reverse("auth-csrf")
        self.login_url = reverse("auth-login")
        self.logout_url = reverse("auth-logout")
        self.me_url = reverse("auth-me")

    def get_csrf_token(self):
        response = self.client.get(self.csrf_url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", self.client.cookies)

        return self.client.cookies["csrftoken"].value

    def post_json(self, url, payload, csrf_token=None):
        headers = {}

        if csrf_token:
            headers["HTTP_X_CSRFTOKEN"] = csrf_token

        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def test_csrf_endpoint_sets_cookie(self):
        response = self.client.get(self.csrf_url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)

    def test_login_rejects_request_without_csrf_token(self):
        response = self.post_json(
            self.login_url,
            {
                "email": self.user.email,
                "password": "SecureTestPassword123!",
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_login_with_valid_credentials(self):
        csrf_token = self.get_csrf_token()

        response = self.post_json(
            self.login_url,
            {
                "email": self.user.email,
                "password": "SecureTestPassword123!",
            },
            csrf_token=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["user"]["email"],
            self.user.email,
        )

        # La respuesta no debe incluir la contraseña.
        self.assertNotIn("password", response.json()["user"])

        # Confirmar que la sesión permite consultar al usuario.
        current_user_response = self.client.get(self.me_url)

        self.assertEqual(current_user_response.status_code, 200)
        self.assertEqual(
            current_user_response.json()["user"]["email"],
            self.user.email,
        )

    def test_login_rejects_invalid_credentials(self):
        csrf_token = self.get_csrf_token()

        response = self.post_json(
            self.login_url,
            {
                "email": self.user.email,
                "password": "WrongPassword123!",
            },
            csrf_token=csrf_token,
        )

        self.assertEqual(response.status_code, 401)

    def test_login_rejects_missing_credentials(self):
        csrf_token = self.get_csrf_token()

        response = self.post_json(
            self.login_url,
            {
                "email": self.user.email,
            },
            csrf_token=csrf_token,
        )

        self.assertEqual(response.status_code, 400)

    def test_current_user_rejects_anonymous_session(self):
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, 401)

    def test_logout_closes_session(self):
        csrf_token = self.get_csrf_token()

        login_response = self.post_json(
            self.login_url,
            {
                "email": self.user.email,
                "password": "SecureTestPassword123!",
            },
            csrf_token=csrf_token,
        )

        self.assertEqual(login_response.status_code, 200)

        # Django puede rotar el token CSRF después del login.
        current_csrf_token = self.client.cookies["csrftoken"].value

        logout_response = self.post_json(
            self.logout_url,
            {},
            csrf_token=current_csrf_token,
        )

        self.assertEqual(logout_response.status_code, 200)

        current_user_response = self.client.get(self.me_url)

        self.assertEqual(current_user_response.status_code, 401)

    def test_logout_rejects_request_without_csrf_token(self):
        csrf_token = self.get_csrf_token()

        login_response = self.post_json(
            self.login_url,
            {
                "email": self.user.email,
                "password": "SecureTestPassword123!",
            },
            csrf_token=csrf_token,
        )

        self.assertEqual(login_response.status_code, 200)

        # No enviamos el token en la petición de cierre.
        response = self.post_json(
            self.logout_url,
            {},
        )

        self.assertEqual(response.status_code, 403)

        # El intento rechazado no debería cerrar la sesión.
        current_user_response = self.client.get(self.me_url)

        self.assertEqual(current_user_response.status_code, 200)

    def test_login_rejects_invalid_json(self):
        csrf_token = self.get_csrf_token()

        response = self.client.post(
            self.login_url,
            data="{invalid-json",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 400)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PASSWORD_RESET_TIMEOUT=3600,
)
class PasswordResetFlowTests(TestCase):
    """Pruebas del flujo completo de recuperación de contraseñas."""

    def setUp(self):
        cache.clear()
        mail.outbox = []

        self.client = Client(enforce_csrf_checks=True)

        self.user = User.objects.create_user(
            email="usuario.reset@example.com",
            password="OldSecurePassword123!",
            first_name="Usuario",
            last_name="Recuperación",
        )

        self.request_url = reverse("password-reset-request")
        self.confirm_url = reverse("password-reset-confirm")
        self.me_url = reverse("auth-me")
        self.csrf_url = reverse("auth-csrf")

    def get_csrf_token(self):
        response = self.client.get(self.csrf_url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", self.client.cookies)

        return self.client.cookies["csrftoken"].value

    def post_json(self, url, payload, include_csrf=True):
        headers = {}

        if include_csrf:
            csrf_cookie = self.client.cookies.get("csrftoken")

            if csrf_cookie is not None:
                headers["HTTP_X_CSRFTOKEN"] = csrf_cookie.value

        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def request_reset(self, email=None):
        self.get_csrf_token()

        return self.post_json(
            self.request_url,
            {
                "email": email or self.user.email,
            },
        )

    def get_reset_credentials_from_email(self):
        self.assertTrue(mail.outbox)

        # El enlace se incluye en el cuerpo del correo de desarrollo.
        links = [
            line.strip() for line in mail.outbox[-1].body.splitlines() if "/reset-password#" in line
        ]

        self.assertTrue(
            links,
            "El correo no contiene el enlace de recuperación.",
        )

        link = urlparse(links[0])
        self.assertNotIn("token", parse_qs(link.query))
        self.assertNotIn("uid", parse_qs(link.query))
        query = parse_qs(link.fragment)

        return {
            "uid": query["uid"][0],
            "token": query["token"][0],
        }

    def test_existing_email_sends_reset_link(self):
        response = self.request_reset()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(
            mail.outbox[0].to,
            [self.user.email],
        )

        self.assertIn(
            "restablecer",
            mail.outbox[0].subject.lower(),
        )

        credentials = self.get_reset_credentials_from_email()

        self.assertIn("uid", credentials)
        self.assertIn("token", credentials)

    def test_unknown_email_does_not_reveal_account_existence(self):
        known_response = self.request_reset(self.user.email)

        unknown_response = self.post_json(
            self.request_url,
            {"email": "inexistente@example.com"},
        )

        self.assertEqual(known_response.status_code, 200)
        self.assertEqual(unknown_response.status_code, 200)

        self.assertEqual(
            known_response.json(),
            unknown_response.json(),
        )

        # Solo la cuenta existente debe recibir un correo.
        self.assertEqual(len(mail.outbox), 1)

    def test_password_can_be_reset_and_token_cannot_be_reused(self):
        response = self.request_reset()

        self.assertEqual(response.status_code, 200)

        credentials = self.get_reset_credentials_from_email()

        self.get_csrf_token()

        new_password = "NewSecurePassword2026!"

        confirm_response = self.post_json(
            self.confirm_url,
            {
                **credentials,
                "password": new_password,
                "password_confirm": new_password,
            },
        )

        self.assertEqual(
            confirm_response.status_code,
            200,
            confirm_response.content,
        )

        self.user.refresh_from_db()

        self.assertTrue(self.user.check_password(new_password))
        self.assertFalse(self.user.check_password("OldSecurePassword123!"))

        # Un token utilizado deja de ser válido.
        reuse_response = self.post_json(
            self.confirm_url,
            {
                **credentials,
                "password": "AnotherSecurePassword2026!",
                "password_confirm": "AnotherSecurePassword2026!",
            },
        )

        self.assertEqual(reuse_response.status_code, 400)

        self.user.refresh_from_db()

        self.assertTrue(self.user.check_password(new_password))

    def test_mismatched_passwords_are_rejected(self):
        credentials = {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": default_token_generator.make_token(self.user),
        }

        self.get_csrf_token()

        response = self.post_json(
            self.confirm_url,
            {
                **credentials,
                "password": "FirstSecurePassword2026!",
                "password_confirm": "DifferentSecurePassword2026!",
            },
        )

        self.assertEqual(response.status_code, 400)

        self.user.refresh_from_db()

        self.assertTrue(self.user.check_password("OldSecurePassword123!"))

    def test_invalid_token_is_rejected(self):
        credentials = {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": "invalid-token",
        }

        self.get_csrf_token()

        response = self.post_json(
            self.confirm_url,
            {
                **credentials,
                "password": "NewSecurePassword2026!",
                "password_confirm": "NewSecurePassword2026!",
            },
        )

        self.assertEqual(response.status_code, 400)

        self.user.refresh_from_db()

        self.assertTrue(self.user.check_password("OldSecurePassword123!"))

    def test_weak_password_is_rejected(self):
        credentials = {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": default_token_generator.make_token(self.user),
        }

        self.get_csrf_token()

        response = self.post_json(
            self.confirm_url,
            {
                **credentials,
                "password": "123",
                "password_confirm": "123",
            },
        )

        self.assertEqual(response.status_code, 400)

        self.user.refresh_from_db()

        self.assertTrue(self.user.check_password("OldSecurePassword123!"))

    def test_reset_request_requires_csrf(self):
        response = self.post_json(
            self.request_url,
            {"email": self.user.email},
            include_csrf=False,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_confirmation_requires_csrf(self):
        credentials = {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": default_token_generator.make_token(self.user),
        }

        response = self.post_json(
            self.confirm_url,
            {
                **credentials,
                "password": "NewSecurePassword2026!",
                "password_confirm": "NewSecurePassword2026!",
            },
            include_csrf=False,
        )

        self.assertEqual(response.status_code, 403)

        self.user.refresh_from_db()

        self.assertTrue(self.user.check_password("OldSecurePassword123!"))

    def test_reset_invalidates_previous_session(self):
        # Un cliente independiente mantiene una sesión autenticada.
        previous_session = Client()

        self.assertTrue(
            previous_session.login(
                email=self.user.email,
                password="OldSecurePassword123!",
            )
        )

        self.assertEqual(
            previous_session.get(self.me_url).status_code,
            200,
        )

        # Solicitar el enlace y recuperar sus credenciales.
        response = self.request_reset()

        self.assertEqual(response.status_code, 200)

        credentials = self.get_reset_credentials_from_email()
        self.get_csrf_token()

        new_password = "NewSecurePassword2026!"

        response = self.post_json(
            self.confirm_url,
            {
                **credentials,
                "password": new_password,
                "password_confirm": new_password,
            },
        )

        self.assertEqual(response.status_code, 200)

        # La sesión anterior debe dejar de autenticar al usuario.
        old_session_response = previous_session.get(self.me_url)

        self.assertEqual(old_session_response.status_code, 401)

    def test_expired_token_is_rejected(self):
        credentials = {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": default_token_generator.make_token(self.user),
        }

        self.get_csrf_token()

        new_password = "NewSecurePassword2026!"

        # Simulamos un token que ya superó su tiempo de validez.
        with self.settings(PASSWORD_RESET_TIMEOUT=-1):
            response = self.post_json(
                self.confirm_url,
                {
                    **credentials,
                    "password": new_password,
                    "password_confirm": new_password,
                },
            )

        self.assertEqual(response.status_code, 400)

        self.user.refresh_from_db()

        self.assertTrue(self.user.check_password("OldSecurePassword123!"))

    def test_reset_requests_are_rate_limited(self):
        self.get_csrf_token()

        responses = [
            self.post_json(
                self.request_url,
                {"email": self.user.email},
            )
            for _ in range(RESET_REQUEST_LIMIT + 1)
        ]

        self.assertTrue(
            all(response.status_code == 200 for response in responses[:RESET_REQUEST_LIMIT])
        )

        self.assertEqual(
            responses[-1].status_code,
            429,
        )

        # Solo se enviaron correos para las solicitudes permitidas.
        self.assertEqual(
            len(mail.outbox),
            RESET_REQUEST_LIMIT,
        )
