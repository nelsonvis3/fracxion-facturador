import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from auditlog.models import AuditEvent


class SecurityEventsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            email="events@example.com", password="SyntheticEventsPassword2026!"
        )

    def login(self, password="SyntheticEventsPassword2026!", **extra):
        return self.client.post(
            "/api/auth/login/",
            json.dumps({"email": self.user.email, "password": password}),
            content_type="application/json",
            **extra,
        )

    def test_login_logout_events_do_not_store_credentials_or_session_tokens(self):
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 200)
        events = AuditEvent.objects.filter(
            entity_type="accounts.security", action__in=["login", "logout"]
        )
        self.assertEqual(events.count(), 2)
        for event in events:
            self.assertIsNone(event.tenant)
            self.assertEqual(event.actor, self.user)
            serialized = json.dumps({"changes": event.changes, "metadata": event.metadata})
            for secret in [
                self.user.email,
                "SyntheticEventsPassword2026!",
                "sessionid",
                "csrfToken",
            ]:
                self.assertNotIn(secret, serialized)

    def test_account_limit_applies_across_ips(self):
        for n in range(20):
            self.assertEqual(
                self.login(password="wrong", REMOTE_ADDR=f"192.0.2.{n + 1}").status_code, 401
            )
        self.assertEqual(self.login(REMOTE_ADDR="198.51.100.1").status_code, 429)

    def test_admin_login_has_its_own_limit(self):
        for _ in range(10):
            self.assertEqual(
                self.client.post(
                    "/admin/login/", {"username": "unknown@example.com", "password": "wrong"}
                ).status_code,
                200,
            )
        self.assertEqual(
            self.client.post(
                "/admin/login/", {"username": "unknown@example.com", "password": "wrong"}
            ).status_code,
            429,
        )

    def test_denied_request_audits_are_bounded(self):
        for _ in range(25):
            self.assertEqual(self.client.get("/api/auth/tenants/").status_code, 401)
        self.assertEqual(AuditEvent.objects.filter(action="permission_denied").count(), 20)
