import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from .signup_code import MAX_ATTEMPTS, issue_code
from .testing import create_verified_user

PASSWORD = "SyntheticSignupCodePassword2026!"


class SignupCodeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.token = self.client.get("/api/auth/csrf/").json()["csrfToken"]
        self.user = get_user_model().objects.create_user(
            email="pending@example.com", password=PASSWORD
        )

    def post(self, path, payload):
        return self.client.post(
            path,
            json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.token,
        )

    def confirm(self, code, email="pending@example.com"):
        return self.post("/api/auth/signup-code/confirm/", {"email": email, "code": code})

    def login(self):
        return self.post("/api/auth/login/", {"email": self.user.email, "password": PASSWORD})

    def test_code_is_stored_only_as_hmac_and_opens_one_session(self):
        code = issue_code(self.user)
        self.user.refresh_from_db()
        self.assertNotIn(code, self.user.email_code_hash)
        response = self.confirm(code)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["email"], self.user.email)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)
        self.assertEqual(self.user.email_code_hash, "")
        self.client.logout()
        self.token = self.client.get("/api/auth/csrf/").json()["csrfToken"]
        self.assertEqual(self.confirm(code).status_code, 400)

    def test_wrong_codes_are_counted_and_exhaust_the_code(self):
        code = issue_code(self.user)
        wrong = f"{(int(code) + 1) % 1_000_000:06d}"
        for _ in range(MAX_ATTEMPTS):
            self.assertEqual(self.confirm(wrong).status_code, 400)
        self.assertEqual(self.confirm(code).status_code, 400)
        self.assertFalse(get_user_model().objects.get(pk=self.user.pk).is_email_verified)

    def test_expired_code_and_malformed_input_are_rejected(self):
        code = issue_code(self.user, now=timezone.now() - timedelta(minutes=16))
        self.assertEqual(self.confirm(code).status_code, 400)
        for bad in ["12345", "1234567", "12a456", "١٢٣٤٥٦", 123456]:
            with self.subTest(bad=bad):
                self.assertEqual(self.confirm(bad).status_code, 400)
        self.assertEqual(self.confirm("123456", email="nobody@example.com").status_code, 400)

    def test_unverified_login_sends_a_code_instead_of_a_session(self):
        response = self.login()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["verification_required"], True)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.assertEqual(len(mail.outbox), 1)
        # A second login inside the cooldown does not mail again.
        self.assertEqual(self.login().status_code, 403)
        self.assertEqual(len(mail.outbox), 1)
        code = mail.outbox[0].subject.rsplit(" ", 1)[-1]
        self.assertEqual(self.confirm(code).status_code, 200)

    def test_wrong_password_never_reveals_pending_state(self):
        response = self.post("/api/auth/login/", {"email": self.user.email, "password": "wrong"})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("verification_required", response.json())
        self.assertEqual(mail.outbox, [])

    def test_resend_is_generic_and_respects_cooldown(self):
        unknown = self.post("/api/auth/signup-code/resend/", {"email": "nobody@example.com"})
        pending = self.post("/api/auth/signup-code/resend/", {"email": self.user.email})
        self.assertEqual(unknown.json(), pending.json())
        self.assertEqual(len(mail.outbox), 1)
        self.post("/api/auth/signup-code/resend/", {"email": self.user.email})
        self.assertEqual(len(mail.outbox), 1)
        verified = create_verified_user(email="done@example.com", password=PASSWORD)
        self.post("/api/auth/signup-code/resend/", {"email": verified.email})
        self.assertEqual(len(mail.outbox), 1)

    def test_delivery_failure_still_creates_account_and_reports_it(self):
        with patch("accounts.signup_code.send_mail", side_effect=OSError("smtp down")):
            response = self.post(
                "/api/auth/register/",
                {
                    "first_name": "Ada",
                    "company_name": "Empresa",
                    "email": "fails@example.com",
                    "password": PASSWORD,
                    "password_confirm": PASSWORD,
                },
            )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["email_sent"])

    def test_confirm_requires_csrf(self):
        code = issue_code(self.user)
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            "/api/auth/signup-code/confirm/",
            json.dumps({"email": self.user.email, "code": code}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
