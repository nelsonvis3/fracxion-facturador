import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings

from auditlog.models import AuditEvent
from tenancy.models import Membership, Tenant

from .registration import REGISTRATION_LIMIT, RegistrationSerializer, register_account

User = get_user_model()


def registration_data(**changes):
    return {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "company_name": "Empresa de prueba",
        "email": "new.owner@example.com",
        "password": "SyntheticRegistrationPassword2026!",
        "password_confirm": "SyntheticRegistrationPassword2026!",
        **changes,
    }


class RegistrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.token = self.client.get("/api/auth/csrf/").json()["csrfToken"]

    def register(self, data=None, csrf=True):
        return self.client.post(
            "/api/auth/register/",
            json.dumps(registration_data() if data is None else data),
            content_type="application/json",
            **({"HTTP_X_CSRFTOKEN": self.token} if csrf else {}),
        )

    def test_registration_creates_account_company_owner_and_session(self):
        response = self.register(registration_data(email="  NEW.OWNER@EXAMPLE.COM  "))
        self.assertEqual(response.status_code, 201)
        user = User.objects.get()
        tenant = Tenant.objects.get()
        membership = Membership.objects.get()
        self.assertEqual(user.email, "new.owner@example.com")
        self.assertEqual(user.first_name, "Ada")
        self.assertEqual(user.last_name, "Lovelace")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password(registration_data()["password"]))
        self.assertNotEqual(user.password, registration_data()["password"])
        self.assertEqual(membership.tenant, tenant)
        self.assertEqual(membership.user, user)
        self.assertEqual(membership.role, Membership.Role.OWNER)
        self.assertEqual(response.json()["tenant"]["id"], str(tenant.pk))
        self.assertEqual(self.client.get("/api/auth/me/").json()["user"]["id"], str(user.pk))
        self.assertEqual(
            self.client.get("/api/auth/tenants/").json()["results"],
            [response.json()["tenant"]],
        )
        self.assertEqual(self.client.get(f"/api/tenants/{tenant.pk}/customers/").status_code, 200)

    def test_registration_requires_csrf_and_creates_nothing_when_missing(self):
        self.assertEqual(self.register(csrf=False).status_code, 403)
        self.assertFalse(User.objects.exists())
        self.assertFalse(Tenant.objects.exists())

    def test_csrf_rotates_and_private_response_omits_passwords(self):
        response = self.register()
        body = response.json()
        self.assertNotEqual(body["csrfToken"], self.token)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        self.assertNotIn("password", json.dumps(body))
        self.assertEqual(
            self.client.post(
                "/api/auth/logout/",
                "{}",
                content_type="application/json",
                HTTP_X_CSRFTOKEN=self.token,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/logout/",
                "{}",
                content_type="application/json",
                HTTP_X_CSRFTOKEN=body["csrfToken"],
            ).status_code,
            200,
        )

    def test_django_password_policy_is_applied(self):
        for password in [
            "short",
            "password123",
            "123456789012",
            "new.owner@example.com",
            "        ",
        ]:
            with self.subTest(password=password):
                response = self.register(
                    registration_data(password=password, password_confirm=password)
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("password", response.json())
        self.assertFalse(User.objects.exists())

    def test_password_confirmation_is_required_and_must_match(self):
        for changes in [{"password_confirm": "DifferentPassword2026!"}, {"password_confirm": ""}]:
            with self.subTest(changes=changes):
                response = self.register(registration_data(**changes))
                self.assertEqual(response.status_code, 400)
                self.assertIn("password_confirm", response.json())
        self.assertFalse(Tenant.objects.exists())

    def test_duplicate_email_cannot_create_company_or_take_over_session(self):
        existing = User.objects.create_user(
            email="new.owner@example.com", password="ExistingPassword2026!"
        )
        response = self.register(registration_data(email="NEW.OWNER@EXAMPLE.COM"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json())
        self.assertEqual(User.objects.count(), 1)
        existing.refresh_from_db()
        self.assertTrue(existing.check_password("ExistingPassword2026!"))
        self.assertFalse(Tenant.objects.exists())
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_invalid_email_and_names_are_rejected(self):
        for changes, field in [
            ({"email": "invalid"}, "email"),
            ({"email": "x" * 250 + "@example.com"}, "email"),
            ({"first_name": " "}, "first_name"),
            ({"first_name": "x" * 151}, "first_name"),
            ({"last_name": "x" * 151}, "last_name"),
            ({"company_name": " "}, "company_name"),
            ({"company_name": "x" * 151}, "company_name"),
            ({"company_name": "invalid\x00name"}, "company_name"),
            ({"password": "x" * 129}, "password"),
        ]:
            with self.subTest(field=field, changes=changes):
                response = self.register(registration_data(**changes))
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())
        self.assertFalse(User.objects.exists())

    def test_last_name_is_optional(self):
        data = registration_data()
        del data["last_name"]
        self.assertEqual(self.register(data).status_code, 201)
        self.assertEqual(User.objects.get().last_name, "")

    def test_missing_required_fields_and_invalid_json_create_nothing(self):
        for payload in [{}, [], None]:
            response = self.client.post(
                "/api/auth/register/",
                json.dumps(payload),
                content_type="application/json",
                HTTP_X_CSRFTOKEN=self.token,
            )
            self.assertEqual(response.status_code, 400)
        response = self.client.post(
            "/api/auth/register/",
            "{invalid",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_registration_rejects_role_privilege_and_existing_tenant_fields(self):
        tenant = Tenant.objects.create(name="Otra empresa", slug="other")
        for fields in [
            {"is_staff": True},
            {"is_superuser": True},
            {"role": "admin"},
            {"tenant": str(tenant.pk)},
        ]:
            response = self.register(registration_data(**fields))
            self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())
        self.assertFalse(Membership.objects.exists())
        self.assertEqual(Tenant.objects.count(), 1)

    def test_rate_limit_includes_failed_attempts(self):
        for _ in range(REGISTRATION_LIMIT):
            self.assertEqual(self.register({}).status_code, 400)
        response = self.register()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "900")
        self.assertFalse(User.objects.exists())

    def test_authenticated_account_cannot_register_another_account(self):
        user = User.objects.create_user(email="logged@example.com")
        self.client.force_login(user)
        self.token = self.client.get("/api/auth/csrf/").json()["csrfToken"]
        self.assertEqual(self.register().status_code, 403)
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(Tenant.objects.exists())
        self.assertEqual(self.client.get("/api/auth/me/").json()["user"]["id"], str(user.pk))

    def test_registration_only_accepts_post(self):
        self.assertEqual(self.client.get("/api/auth/register/").status_code, 405)
        self.assertEqual(
            self.client.put("/api/auth/register/", HTTP_X_CSRFTOKEN=self.token).status_code, 405
        )

    def test_company_names_can_repeat_and_unicode_name_has_valid_unique_slug(self):
        _, first = register_account(data=registration_data(company_name="会社"))
        _, second = register_account(
            data=registration_data(company_name="会社", email="second@example.com")
        )
        self.assertEqual(first.name, second.name)
        self.assertNotEqual(first.slug, second.slug)
        self.assertTrue(first.slug.startswith("empresa-"))

    def test_membership_failure_rolls_back_account_and_company(self):
        with patch(
            "accounts.registration.Membership.objects.create", side_effect=RuntimeError("failure")
        ):
            with self.assertRaises(RuntimeError):
                register_account(data=registration_data())
        self.assertFalse(User.objects.exists())
        self.assertFalse(Tenant.objects.exists())

    def test_audit_failure_rolls_back_all_registration_records(self):
        with patch("accounts.registration.record_audit_event", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                register_account(data=registration_data())
        self.assertFalse(User.objects.exists())
        self.assertFalse(Tenant.objects.exists())
        self.assertFalse(Membership.objects.exists())

    def test_unexpected_integrity_error_is_not_misreported_as_duplicate_email(self):
        with patch(
            "accounts.registration.Membership.objects.create",
            side_effect=IntegrityError("unexpected"),
        ):
            with self.assertRaises(IntegrityError):
                register_account(data=registration_data())
        self.assertFalse(User.objects.exists())
        self.assertFalse(Tenant.objects.exists())

    def test_onboarding_is_audited_without_password_or_request_body(self):
        self.register()
        event = AuditEvent.objects.get()
        self.assertEqual(event.entity_type, "tenancy.tenant")
        self.assertEqual(event.tenant, Tenant.objects.get())
        self.assertEqual(event.actor, User.objects.get())
        self.assertEqual(event.metadata, {"source": "registration"})
        self.assertEqual(event.changes["fields"]["name"]["after"], "Empresa de prueba")
        self.assertNotIn("password", json.dumps(event.changes))
        self.assertNotIn("email", json.dumps(event.changes))

    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.PBKDF2PasswordHasher"])
    def test_registration_uses_configured_password_hasher(self):
        user, _ = register_account(data=registration_data())
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))
        self.assertTrue(user.check_password(registration_data()["password"]))


class ConcurrentRegistrationTests(TransactionTestCase):
    def test_same_email_race_leaves_only_one_account_and_company(self):
        cache.clear()
        barrier = Barrier(2)
        validate_email = RegistrationSerializer.validate_email

        def validate_before_either_insert(serializer, value):
            value = validate_email(serializer, value)
            barrier.wait(timeout=10)
            return value

        def attempt():
            try:
                client = Client(enforce_csrf_checks=True)
                token = client.get("/api/auth/csrf/").json()["csrfToken"]
                response = client.post(
                    "/api/auth/register/",
                    json.dumps(registration_data()),
                    content_type="application/json",
                    HTTP_X_CSRFTOKEN=token,
                )
                return response.status_code
            finally:
                connections.close_all()

        with patch.object(RegistrationSerializer, "validate_email", validate_before_either_insert):
            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(sorted(statuses), [201, 400])
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Tenant.objects.count(), 1)
        self.assertEqual(Membership.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.count(), 1)
