"""Bounded local attack simulations; never target external hosts or real accounts."""

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tenancy.invitations import token_digest
from tenancy.models import Membership, Tenant, TenantInvitation


class EnterpriseAttackSurfaceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = get_user_model().objects.create_user(email="attack-owner@example.com")
        self.tenant = Tenant.objects.create(name="Synthetic attack target", slug="attack-target")
        self.member = Membership.objects.create(tenant=self.tenant, user=self.owner, role="owner")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.base = f"/api/tenants/{self.tenant.pk}"
        self.invitation = TenantInvitation.objects.create(
            tenant=self.tenant,
            email="target@example.com",
            role="viewer",
            invited_by=self.owner,
            token_digest=token_digest("a" * 43),
            expires_at=timezone.now() + timedelta(days=7),
        )

    def test_security_matrix_for_all_enterprise_operations(self):
        operations = [
            ("get", "/settings/", None),
            ("patch", "/settings/", {"name": "Blocked"}),
            ("get", "/settings/logo/", None),
            ("get", "/members/", None),
            ("patch", f"/members/{self.member.pk}/", {"role": "owner"}),
            ("get", "/invitations/", None),
            ("post", "/invitations/", {"email": "new@example.com", "role": "viewer"}),
            ("post", f"/invitations/{self.invitation.pk}/resend/", {}),
            ("post", f"/invitations/{self.invitation.pk}/revoke/", {}),
            ("get", "/analytics/overview/", None),
            ("get", "/reports/export/", None),
            ("get", "/reports/jobs/", None),
            ("post", "/reports/jobs/", {}),
            ("get", "/automation/rules/", None),
            ("post", "/automation/rules/", {}),
            ("get", "/notifications/", None),
            ("post", "/notifications/00000000-0000-4000-8000-000000000001/read/", {}),
            ("get", "/suppliers/", None),
            ("post", "/suppliers/", {}),
            ("get", "/inventory/items/", None),
            ("patch", "/inventory/items/00000000-0000-4000-8000-000000000001/", {}),
            ("get", "/inventory/movements/", None),
            ("post", "/inventory/movements/", {}),
            ("post", "/inventory/movements/00000000-0000-4000-8000-000000000001/reverse/", {}),
            ("get", "/expenses/", None),
            ("post", "/expenses/", {}),
            ("patch", "/expenses/00000000-0000-4000-8000-000000000001/", {}),
            ("post", "/expenses/00000000-0000-4000-8000-000000000001/post/", {}),
            ("post", "/expenses/00000000-0000-4000-8000-000000000001/void/", {}),
            ("get", "/expenses/00000000-0000-4000-8000-000000000001/attachment/", None),
            ("post", "/expenses/00000000-0000-4000-8000-000000000001/payments/", {}),
            ("post", "/expense-payments/00000000-0000-4000-8000-000000000001/reverse/", {}),
            ("get", "/expenses/categories/", None),
            ("post", "/expenses/categories/", {}),
        ]
        outsider = get_user_model().objects.create_user(email="outsider@example.com")
        for condition in [
            "anonymous",
            "outsider",
            "inactive-user",
            "inactive-member",
            "inactive-tenant",
        ]:
            self.client.force_authenticate(
                None
                if condition == "anonymous"
                else outsider
                if condition == "outsider"
                else self.owner
            )
            obj = {
                "inactive-user": self.owner,
                "inactive-member": self.member,
                "inactive-tenant": self.tenant,
            }.get(condition)
            if obj:
                obj.is_active = False
                obj.save()
            for method, suffix, data in operations:
                with self.subTest(condition=condition, method=method, suffix=suffix):
                    response = getattr(self.client, method)(self.base + suffix, data, format="json")
                    self.assertEqual(response.status_code, 401 if condition == "anonymous" else 403)
            if obj:
                obj.is_active = True
                obj.save()
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(self.base + "/members/").status_code, 200)
        self.assertEqual(self.client.get(self.base + "/invitations/").status_code, 200)

    def test_malformed_mutations_never_turn_into_500(self):
        samples = [
            None,
            [],
            ["nested"],
            True,
            123,
            "text",
            {"is_superuser": True},
            {"role": "superuser"},
            {"__proto__": {"is_staff": True}},
            {"timezone": "../../etc/passwd"},
            {"logo_data": "data:image/svg+xml,<svg/>"},
        ]
        for path, method in [
            ("/settings/", "patch"),
            ("/invitations/", "post"),
            (f"/members/{self.member.pk}/", "patch"),
            ("/suppliers/", "post"),
            ("/inventory/movements/", "post"),
            ("/expenses/", "post"),
            ("/expenses/categories/", "post"),
            ("/automation/rules/", "post"),
            ("/reports/jobs/", "post"),
        ]:
            for sample in samples:
                with self.subTest(path=path, sample=type(sample).__name__):
                    response = getattr(self.client, method)(
                        self.base + path, json.dumps(sample), content_type="application/json"
                    )
                    self.assertIn(response.status_code, [200, 400, 403, 429])
        self.owner.refresh_from_db()
        self.member.refresh_from_db()
        self.assertFalse(self.owner.is_superuser)
        self.assertFalse(self.owner.is_staff)
        self.assertEqual(self.member.role, "owner")
        self.assertTrue(self.member.is_active)

    def test_token_fuzzing_is_generic_and_bounded(self):
        self.client.force_authenticate(None)
        for token in [
            "",
            "short",
            "x" * 1000,
            "x" * 43,
            "<script>" * 8,
            "../" * 20,
            {"$ne": None},
            ["a" * 43],
            None,
        ]:
            response = self.client.post(
                "/api/auth/invitations/preview/", {"token": token}, format="json"
            )
            self.assertEqual(response.status_code, 400)
            self.assertNotIn(self.invitation.email, str(response.data))
