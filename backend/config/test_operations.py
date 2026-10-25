from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings

from config.middleware import TrustedProxyMiddleware
from tenancy.models import Membership, Tenant


class OperationsTests(TestCase):
    def test_health_and_ready(self):
        self.assertEqual(self.client.get("/health/").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/ready/").json(), {"status": "ok"})

    def test_ready_returns_503_without_error_details(self):
        with patch("config.health.cache.set", side_effect=RuntimeError("private error")):
            response = self.client.get("/ready/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})

    @override_settings(TRUSTED_PROXY_NETWORKS=["172.29.33.10/32"])
    def test_only_trusted_proxy_can_set_client_ip(self):
        for observed, expected in [("172.29.33.10", "203.0.113.9"), ("203.0.113.2", "203.0.113.2")]:
            request = RequestFactory().get(
                "/",
                REMOTE_ADDR=observed,
                HTTP_X_CLIENT_IP="203.0.113.9",
                HTTP_X_FORWARDED_PROTO="https",
            )
            TrustedProxyMiddleware(lambda request: HttpResponse())(request)
            self.assertEqual(request.META["REMOTE_ADDR"], expected)
            if observed != "172.29.33.10":
                self.assertNotIn("HTTP_X_FORWARDED_PROTO", request.META)

    @override_settings(TRUSTED_PROXY_NETWORKS=["172.29.33.10/32"])
    def test_invalid_forwarded_ip_keeps_observed_address(self):
        request = RequestFactory().get("/", REMOTE_ADDR="172.29.33.10", HTTP_X_CLIENT_IP="invalid")
        TrustedProxyMiddleware(lambda request: HttpResponse())(request)
        self.assertEqual(request.META["REMOTE_ADDR"], "172.29.33.10")

    @patch(
        "tenancy.management.commands.create_workspace.getpass",
        side_effect=["AStrongSetupPassword2026!", "AStrongSetupPassword2026!"],
    )
    def test_workspace_creates_normal_owner(self, prompt):
        call_command(
            "create_workspace",
            email="owner@example.com",
            name="Workspace",
            slug="workspace",
            stdout=StringIO(),
        )
        user = get_user_model().objects.get(email="owner@example.com")
        self.assertTrue(user.check_password("AStrongSetupPassword2026!"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(Membership.objects.get(user=user).role, "owner")

    def test_workspace_can_use_existing_account(self):
        get_user_model().objects.create_user(email="owner@example.com")
        call_command(
            "create_workspace",
            email="owner@example.com",
            name="Workspace",
            slug="workspace",
            stdout=StringIO(),
        )
        self.assertEqual(get_user_model().objects.count(), 1)

    @patch("tenancy.management.commands.create_workspace.getpass", side_effect=["a", "b"])
    def test_workspace_mismatch_is_atomic(self, prompt):
        with self.assertRaises(CommandError):
            call_command(
                "create_workspace", email="owner@example.com", name="Workspace", slug="workspace"
            )
        self.assertFalse(Tenant.objects.exists())
        self.assertFalse(get_user_model().objects.exists())

    def test_admin_user_form_supports_email_without_username(self):
        user = get_user_model().objects.create_superuser(
            email="staff@example.com", password="AStrongSetupPassword2026!"
        )
        self.client = Client()
        self.client.force_login(user)
        self.assertEqual(self.client.get("/admin/accounts/user/add/").status_code, 200)
