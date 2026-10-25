import json
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.core.cache import cache
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from auditlog.models import AuditEvent

from .email_verification import MAX_AGE, verification_token

User = get_user_model()
BASE = "/api/auth/email-verification/"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailVerificationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="verify-owner@example.com", password="SyntheticVerifyPassword2026!"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def request_token(self):
        response = self.client.post(BASE + "request/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mail.outbox[-1].to, [self.user.email])
        return re.search(r"#token=(\S+)", mail.outbox[-1].body).group(1)

    def test_delivery_confirmation_one_use_and_transactional_audit(self):
        self.assertFalse(self.client.get(BASE).data["verified"])

        token = self.request_token()
        self.assertNotIn(token, json.dumps(self.client.get(BASE).data))
        self.assertEqual(
            self.client.post(BASE + "confirm/", {"token": token}, format="json").status_code, 200
        )
        self.assertTrue(self.client.get(BASE).data["verified"])
        self.assertEqual(
            self.client.post(BASE + "confirm/", {"token": token}, format="json").status_code, 400
        )
        events = AuditEvent.objects.filter(entity_type="accounts.security")
        self.assertTrue(
            events.filter(
                metadata__event="email_verification", metadata__outcome="verified"
            ).exists()
        )
        for event in events:
            payload = json.dumps(event.metadata)
            self.assertNotIn(token, payload)
            self.assertNotIn(self.user.email, payload)
        self.assertEqual(self.client.post(BASE + "request/", {}, format="json").status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_invalidates_old_link_and_tampering_cannot_confirm(self):
        old = self.request_token()
        new = self.request_token()
        self.assertNotEqual(old, new)
        for token in [
            old,
            new + "x",
            "invalid",
            signing.dumps({"user": self.user.pk}, salt="different-purpose"),
        ]:
            self.assertEqual(
                self.client.post(BASE + "confirm/", {"token": token}, format="json").status_code,
                400,
            )
        self.assertEqual(
            self.client.post(BASE + "confirm/", {"token": new}, format="json").status_code, 200
        )

    def test_expiration_changed_email_and_disabled_account_invalidate_links(self):
        token = self.request_token()
        with patch(
            "accounts.email_verification.signing.loads", side_effect=signing.SignatureExpired
        ):
            self.assertEqual(
                self.client.post(BASE + "confirm/", {"token": token}, format="json").status_code,
                400,
            )
        User.objects.filter(pk=self.user.pk).update(email="changed@example.com")
        self.assertEqual(
            self.client.post(BASE + "confirm/", {"token": token}, format="json").status_code, 400
        )
        self.user.refresh_from_db()
        token = verification_token(self.user)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        anonymous = APIClient()
        self.assertEqual(
            anonymous.post(BASE + "confirm/", {"token": token}, format="json").status_code, 400
        )

    def test_real_signature_age_limit(self):
        import time

        now = time.time()
        self.user.refresh_from_db()
        with patch("django.core.signing.time.time", return_value=now - MAX_AGE - 60):
            token = verification_token(self.user)
        self.assertEqual(
            self.client.post(BASE + "confirm/", {"token": token}, format="json").status_code, 400
        )

    def test_other_account_cannot_confirm_or_choose_recipient(self):
        token = self.request_token()
        other = User.objects.create_user(email="verify-other@example.com")
        self.client.force_authenticate(other)
        self.assertEqual(
            self.client.post(BASE + "confirm/", {"token": token}, format="json").status_code, 400
        )
        self.assertEqual(
            self.client.post(
                BASE + "request/", {"email": self.user.email}, format="json"
            ).status_code,
            400,
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_email_verified)

    def test_anonymous_needs_csrf_and_token_and_is_never_logged_in(self):
        token = self.request_token()
        anonymous = Client(enforce_csrf_checks=True)
        self.assertEqual(
            anonymous.post(
                BASE + "confirm/", json.dumps({"token": token}), content_type="application/json"
            ).status_code,
            403,
        )
        csrf = anonymous.get("/api/auth/csrf/").json()["csrfToken"]
        response = anonymous.post(
            BASE + "confirm/",
            json.dumps({"token": token}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", anonymous.session)
        self.assertEqual(anonymous.get(BASE).status_code, 401)
        self.assertEqual(
            anonymous.post(
                BASE + "request/", "{}", content_type="application/json", HTTP_X_CSRFTOKEN=csrf
            ).status_code,
            401,
        )

    def test_transport_failure_is_reported_and_never_logs_token_or_smtp_secret(self):
        with (
            patch(
                "accounts.email_verification.send_mail",
                side_effect=RuntimeError("SYNTHETIC_SMTP_SECRET"),
            ),
            patch("accounts.email_verification.logger"),
        ):
            response = self.client.post(BASE + "request/", {}, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("SYNTHETIC_SMTP_SECRET", response.content.decode())
        self.assertTrue(
            AuditEvent.objects.filter(
                metadata__event="email_verification_delivery", metadata__outcome="failed"
            ).exists()
        )
        self.assertFalse(self.client.get(BASE).data["verified"])

    def test_rate_limit_and_email_change_remove_verified_status(self):
        token = self.request_token()
        for _ in range(4):
            self.request_token()
        self.assertEqual(self.client.post(BASE + "request/", {}, format="json").status_code, 429)
        self.assertEqual(
            self.client.post(BASE + "confirm/", {"token": token}, format="json").status_code, 400
        )
        self.user.refresh_from_db()
        token = verification_token(self.user)
        self.assertEqual(
            self.client.post(BASE + "confirm/", {"token": token}, format="json").status_code, 200
        )
        User.objects.filter(pk=self.user.pk).update(email="verified-now-changed@example.com")
        self.assertFalse(self.client.get(BASE).data["verified"])


class VerificationConcurrencyTests(TransactionTestCase):
    def test_simultaneous_confirmation_consumes_token_only_once(self):
        cache.clear()
        user = User.objects.create_user(email="simultaneous-verification@example.com")
        token = verification_token(user)
        barrier = Barrier(2)

        def confirm():
            try:
                client = APIClient()
                barrier.wait(timeout=10)
                return client.post(BASE + "confirm/", {"token": token}, format="json").status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: confirm(), range(2)))
        self.assertCountEqual(results, [200, 400])
        self.assertEqual(
            AuditEvent.objects.filter(
                metadata__event="email_verification", metadata__outcome="verified"
            ).count(),
            1,
        )
