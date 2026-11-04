import json

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from billing.models import Invoice
from tenancy.models import Membership, Tenant

DEMO = "demo@fracxion.invalid"


@override_settings(DEMO_LOGIN_EMAIL=DEMO)
class DemoLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        call_command("seed_demo", stdout=open("/dev/null", "w"))
        self.tenant = Tenant.objects.get(slug="demo-panaderia-la-espiga")

    def client_with_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.token = client.get("/api/auth/csrf/").json()["csrfToken"]
        return client

    def post(self, client, path, payload=None):
        return client.post(
            path,
            json.dumps(payload or {}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=client.token,
        )

    def demo_client(self):
        client = self.client_with_csrf()
        response = self.post(client, "/api/auth/demo/")
        self.assertEqual(response.status_code, 200)
        client.token = response.json()["csrfToken"]
        return client

    def test_seed_is_idempotent_and_has_sample_documents(self):
        call_command("seed_demo", stdout=open("/dev/null", "w"))
        self.assertEqual(Tenant.objects.filter(slug="demo-panaderia-la-espiga").count(), 1)
        self.assertEqual(Invoice.objects.filter(tenant=self.tenant).count(), 6)
        self.assertFalse(get_user_model().objects.get(email=DEMO).has_usable_password())

    def test_demo_session_reads_but_cannot_write(self):
        client = self.demo_client()
        base = f"/api/tenants/{self.tenant.pk}"
        self.assertEqual(client.get(f"{base}/invoices/").status_code, 200)
        created = self.post(client, f"{base}/customers/", {"name": "Intruso"})
        self.assertEqual(created.status_code, 403)
        self.assertEqual(client.get(f"{base}/audit-events/").status_code, 403)

    def test_demo_account_cannot_change_credentials(self):
        client = self.demo_client()
        changed = self.post(
            client,
            "/api/auth/password/change/",
            {"current_password": "", "password": "Nueva2026!x", "password_confirm": "Nueva2026!x"},
        )
        self.assertEqual(changed.status_code, 400)
        with override_settings(MFA_ENCRYPTION_KEYS=[Fernet.generate_key().decode()]):
            mfa = self.post(client, "/api/auth/mfa/", {"current_password": "anything"})
        self.assertEqual(mfa.status_code, 400)

    def test_visitors_only_see_their_own_session(self):
        first, second = self.demo_client(), self.demo_client()
        sessions = first.get("/api/auth/sessions/").json()
        results = sessions["results"] if isinstance(sessions, dict) else sessions
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["current"])
        self.assertEqual(second.get("/api/auth/me/").status_code, 200)

    def test_demo_refuses_an_account_that_could_write(self):
        user = get_user_model().objects.get(email=DEMO)
        Membership.objects.filter(user=user).update(role=Membership.Role.ADMIN)
        self.assertEqual(self.post(self.client_with_csrf(), "/api/auth/demo/").status_code, 404)

    def test_demo_disabled_without_setting_and_requires_csrf(self):
        with override_settings(DEMO_LOGIN_EMAIL=""):
            self.assertEqual(self.post(self.client_with_csrf(), "/api/auth/demo/").status_code, 404)
        self.assertEqual(Client(enforce_csrf_checks=True).post("/api/auth/demo/").status_code, 403)
