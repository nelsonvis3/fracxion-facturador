import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from auditlog.models import AuditEvent

from .models import AccountSession

User = get_user_model()
PASSWORD = "SyntheticSessionPassword2026!"


class SessionControlTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="session-owner@example.com", password=PASSWORD)
        self.first = Client(HTTP_USER_AGENT="Mozilla Chrome Linux")
        self.second = Client(HTTP_USER_AGENT="Mozilla Firefox Windows")
        for client in [self.first, self.second]:
            self.assertEqual(
                self.post(
                    client, "/api/auth/login/", {"email": self.user.email, "password": PASSWORD}
                ).status_code,
                200,
            )

    def post(self, client, path, data):
        return client.post(path, json.dumps(data), content_type="application/json")

    def test_inventory_is_private_and_never_serializes_session_credentials(self):
        response = self.first.get("/api/auth/sessions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 2)
        self.assertEqual(sum(row["current"] for row in response.json()["results"]), 1)
        for key in Session.objects.values_list("session_key", flat=True):
            self.assertNotIn(key, response.content.decode())
        outsider = User.objects.create_user(email="session-outsider@example.com")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get("/api/auth/sessions/").json()["count"], 1)
        target = AccountSession.objects.filter(user=self.user).first()
        self.assertEqual(
            self.post(self.client, f"/api/auth/sessions/{target.pk}/revoke/", {}).status_code, 404
        )
        self.assertEqual(Client().get("/api/auth/sessions/").status_code, 401)

    def test_targeted_revocation_removes_only_selected_session(self):
        sessions = self.first.get("/api/auth/sessions/").json()["results"]
        other = next(row for row in sessions if not row["current"])
        self.assertEqual(
            self.post(self.first, f"/api/auth/sessions/{other['id']}/revoke/", {}).status_code, 200
        )
        self.assertEqual(self.second.get("/api/auth/me/").status_code, 401)
        self.assertEqual(self.first.get("/api/auth/me/").status_code, 200)

    def test_revoke_others_invalidates_even_untracked_legacy_sessions(self):
        legacy = Client()
        legacy.force_login(self.user)
        self.assertFalse(
            AccountSession.objects.filter(session_id=legacy.session.session_key).exists()
        )
        response = self.post(
            self.first, "/api/auth/sessions/revoke-others/", {"current_password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.first.get("/api/auth/me/").status_code, 200)
        self.assertEqual(self.second.get("/api/auth/me/").status_code, 401)
        self.assertEqual(legacy.get("/api/auth/me/").status_code, 401)
        self.user.refresh_from_db()
        self.assertEqual(self.user.session_version, 1)

    def test_initial_epoch_preserves_django_hash_and_secret_fallback(self):
        self.assertEqual(
            self.user.get_session_auth_hash(), AbstractUser._get_session_auth_hash(self.user)
        )
        self.user.session_version = 1
        with self.settings(SECRET_KEY_FALLBACKS=["synthetic-fallback-only"]):
            fallback = list(self.user.get_session_auth_fallback_hash())
        self.assertEqual(
            fallback, [self.user._get_session_auth_hash(secret="synthetic-fallback-only")]
        )
        self.assertNotEqual(fallback[0], self.user.get_session_auth_hash())

    def test_password_change_requires_current_confirmation_and_preserves_this_device(self):
        url = "/api/auth/password/change/"
        cases = [
            {
                "current_password": "wrong",
                "password": "SyntheticNewPassword2026!",
                "password_confirm": "SyntheticNewPassword2026!",
            },
            {"current_password": PASSWORD, "password": "weak", "password_confirm": "weak"},
            {
                "current_password": PASSWORD,
                "password": "SyntheticNewPassword2026!",
                "password_confirm": "different",
            },
        ]
        for case in cases:
            self.assertEqual(self.post(self.first, url, case).status_code, 400)
        response = self.post(
            self.first,
            url,
            {
                "current_password": PASSWORD,
                "password": "SyntheticNewPassword2026!",
                "password_confirm": "SyntheticNewPassword2026!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("SyntheticNewPassword2026!"))
        self.assertEqual(self.first.get("/api/auth/me/").status_code, 200)
        self.assertEqual(self.second.get("/api/auth/me/").status_code, 401)
        event = AuditEvent.objects.get(metadata__event="password_changed")
        self.assertNotIn("SyntheticNew", str(event.metadata))
        self.assertEqual(event.changes, {})

    def test_current_revocation_and_expired_entries(self):
        key = self.second.session.session_key
        Session.objects.filter(session_key=key).update(
            expire_date=timezone.now() - timedelta(seconds=1)
        )
        response = self.first.get("/api/auth/sessions/").json()
        self.assertEqual(response["count"], 1)
        current = response["results"][0]
        result = self.post(self.first, f"/api/auth/sessions/{current['id']}/revoke/", {})
        self.assertTrue(result.json()["current"])
        self.assertEqual(self.first.get("/api/auth/me/").status_code, 401)

    def test_forged_account_fields_and_password_guessing_are_bounded(self):
        self.assertEqual(
            self.post(
                self.first,
                "/api/auth/sessions/revoke-others/",
                {"current_password": PASSWORD, "user": 999, "is_superuser": True},
            ).status_code,
            400,
        )
        for _ in range(9):
            self.assertEqual(
                self.post(
                    self.first, "/api/auth/sessions/revoke-others/", {"current_password": "wrong"}
                ).status_code,
                400,
            )
        self.assertEqual(
            self.post(
                self.first, "/api/auth/sessions/revoke-others/", {"current_password": PASSWORD}
            ).status_code,
            429,
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.session_version, 0)

    def test_audit_failure_rolls_back_password_change(self):
        with patch(
            "accounts.session_views.security_event",
            side_effect=RuntimeError("synthetic audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.post(
                    self.first,
                    "/api/auth/password/change/",
                    {
                        "current_password": PASSWORD,
                        "password": "SyntheticOtherPassword2026!",
                        "password_confirm": "SyntheticOtherPassword2026!",
                    },
                )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))
