import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from tenancy.models import Membership, Tenant


class MalformedAuthenticationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.token = self.client.get("/api/auth/csrf/").json()["csrfToken"]

    def post(self, path, body):
        return self.client.post(
            path, body, content_type="application/json", HTTP_X_CSRFTOKEN=self.token
        )

    def test_excessive_integer_returns_400_on_every_auth_endpoint(self):
        body = '{"email":' + "9" * 5000 + "}"
        for path in ["login", "register", "password-reset", "password-reset/confirm"]:
            with self.subTest(path=path):
                response = self.post(f"/api/auth/{path}/", body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_invalid_unicode_and_nul_are_rejected_before_authentication(self):
        for value in ["bad\ud800@example.com", "bad\x00@example.com"]:
            for path in ["login", "password-reset"]:
                with self.subTest(value=repr(value), path=path):
                    with patch("accounts.views.authenticate", return_value=None) as authenticate:
                        response = self.post(
                            f"/api/auth/{path}/",
                            json.dumps({"email": value, "password": "SyntheticPassword2026!"}),
                        )
                    self.assertEqual(response.status_code, 400)
                    authenticate.assert_not_called()

    def test_oversized_credentials_do_not_reach_password_hashing(self):
        for fields in [
            {"email": "a" * 255, "password": "SyntheticPassword2026!"},
            {"email": "valid@example.com", "password": "a" * 4097},
        ]:
            with self.subTest(fields={key: len(value) for key, value in fields.items()}):
                with patch("accounts.views.authenticate", return_value=None) as authenticate:
                    response = self.post("/api/auth/login/", json.dumps(fields))
                self.assertEqual(response.status_code, 400)
                authenticate.assert_not_called()

    def test_reset_rejects_oversized_email(self):
        response = self.post("/api/auth/password-reset/", json.dumps({"email": "a" * 255}))
        self.assertEqual(response.status_code, 400)

    def test_reset_rejects_oversized_password_before_token_validation(self):
        user = get_user_model().objects.create_user(email="reset-security@example.com")
        with patch(
            "accounts.password_reset.default_token_generator.check_token", return_value=False
        ) as check_token:
            response = self.post(
                "/api/auth/password-reset/confirm/",
                json.dumps(
                    {
                        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                        "token": "invalid-token",
                        "password": "a" * 4097,
                        "password_confirm": "a" * 4097,
                    }
                ),
            )
        self.assertEqual(response.status_code, 400)
        check_token.assert_not_called()

    def test_deep_json_and_nonfinite_numbers_are_rejected(self):
        for body in [
            '{"email":' + "[" * 101 + "0" + "]" * 101 + "}",
            '{"email":NaN}',
            '{"email":1e999}',
        ]:
            with self.subTest(body_length=len(body)):
                response = self.post("/api/auth/login/", body)
                self.assertEqual(response.status_code, 400)


class MalformedBusinessJsonTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="parser-owner@example.com")
        self.tenant = Tenant.objects.create(name="Parser tests", slug="parser-tests")
        Membership.objects.create(tenant=self.tenant, user=self.user, role="owner")
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.token = self.client.get("/api/auth/csrf/").json()["csrfToken"]

    def test_business_parser_rejects_nested_invalid_unicode(self):
        response = self.client.post(
            f"/api/tenants/{self.tenant.pk}/products/",
            json.dumps({"name": "Valid name", "ignored": {"value": "\ud800"}}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("JSON", response.json()["detail"])

    def test_business_parser_rejects_excessive_nesting(self):
        body = '{"name":"Valid name","ignored":' + "[" * 101 + "0" + "]" * 101 + "}"
        response = self.client.post(
            f"/api/tenants/{self.tenant.pk}/products/",
            body,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("JSON", response.json()["detail"])

    def test_search_rejects_nul_before_database_query(self):
        for resource in ["customers", "products", "invoices"]:
            with self.subTest(resource=resource):
                response = self.client.get(
                    f"/api/tenants/{self.tenant.pk}/{resource}/", {"search": "bad\x00value"}
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_business_parser_bounds_body_size(self):
        from config.parsers import MAX_JSON_BYTES

        response = self.client.post(
            f"/api/tenants/{self.tenant.pk}/products/",
            '{"name":"' + "a" * MAX_JSON_BYTES + '"}',
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 400)
