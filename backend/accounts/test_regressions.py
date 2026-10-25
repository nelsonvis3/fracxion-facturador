import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase

from tenancy.models import Membership, Tenant


class SessionRegressionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            email="session@example.com", password="AstrongTestPassword77!"
        )
        self.client = Client(enforce_csrf_checks=True)

    def test_json_csrf_works_and_login_returns_rotated_token(self):
        token = self.client.get("/api/auth/csrf/").json()["csrfToken"]
        response = self.client.post(
            "/api/auth/login/",
            json.dumps({"email": self.user.email, "password": "AstrongTestPassword77!"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        rotated = response.json()["csrfToken"]
        self.assertNotEqual(token, rotated)
        logout = self.client.post(
            "/api/auth/logout/", "{}", content_type="application/json", HTTP_X_CSRFTOKEN=rotated
        )
        self.assertEqual(logout.status_code, 200)

    def test_old_token_rejected_after_login(self):
        token = self.client.get("/api/auth/csrf/").json()["csrfToken"]
        self.client.post(
            "/api/auth/login/",
            json.dumps({"email": self.user.email, "password": "AstrongTestPassword77!"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/logout/", "{}", content_type="application/json", HTTP_X_CSRFTOKEN=token
            ).status_code,
            403,
        )

    def test_login_is_rate_limited(self):
        token = self.client.get("/api/auth/csrf/").json()["csrfToken"]
        for _ in range(20):
            response = self.client.post(
                "/api/auth/login/",
                json.dumps({"email": "unknown@example.com", "password": "invalid"}),
                content_type="application/json",
                HTTP_X_CSRFTOKEN=token,
            )
            self.assertEqual(response.status_code, 401)
        response = self.client.post(
            "/api/auth/login/",
            json.dumps({"email": "unknown@example.com", "password": "invalid"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)

    def test_tenants_exclude_inactive_membership_and_company(self):
        self.client.force_login(self.user)
        active = Tenant.objects.create(name="Active", slug="active")
        inactive = Tenant.objects.create(name="Inactive", slug="inactive", is_active=False)
        revoked = Tenant.objects.create(name="Revoked", slug="revoked")
        for tenant in [active, inactive, revoked]:
            Membership.objects.create(
                tenant=tenant, user=self.user, role="owner", is_active=tenant != revoked
            )
        rows = self.client.get("/api/auth/tenants/").json()["results"]
        self.assertEqual([row["id"] for row in rows], [str(active.pk)])

    def test_authenticated_api_mutation_requires_csrf(self):
        self.client.force_login(self.user)
        tenant = Tenant.objects.create(name="Security", slug="security")
        Membership.objects.create(tenant=tenant, user=self.user, role="owner")
        response = self.client.post(
            f"/api/tenants/{tenant.pk}/customers/",
            json.dumps({"name": "Customer"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
