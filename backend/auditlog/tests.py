from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from tenancy.models import Membership, Tenant

from .models import AuditEvent

User = get_user_model()


class AuditEventAPITests(APITestCase):
    """Pruebas HTTP para el aislamiento y la lectura de auditoría."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            name="Empresa Alpha",
            slug="empresa-alpha",
        )

        self.tenant_b = Tenant.objects.create(
            name="Empresa Beta",
            slug="empresa-beta",
        )

        self.owner_a = User.objects.create_user(
            email="owner.alpha@example.com",
            password="TestPassword123!",
        )

        self.owner_b = User.objects.create_user(
            email="owner.beta@example.com",
            password="TestPassword123!",
        )

        self.admin_a = User.objects.create_user(
            email="admin.alpha@example.com",
            password="TestPassword123!",
        )

        self.viewer_a = User.objects.create_user(
            email="viewer.alpha@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            tenant=self.tenant_a,
            user=self.owner_a,
            role=Membership.Role.OWNER,
        )

        Membership.objects.create(
            tenant=self.tenant_b,
            user=self.owner_b,
            role=Membership.Role.OWNER,
        )

        Membership.objects.create(
            tenant=self.tenant_a,
            user=self.admin_a,
            role=Membership.Role.ADMIN,
        )

        Membership.objects.create(
            tenant=self.tenant_a,
            user=self.viewer_a,
            role=Membership.Role.VIEWER,
        )

        self.event_a = AuditEvent.objects.create(
            tenant=self.tenant_a,
            actor=self.owner_a,
            action=AuditEvent.Action.CREATE,
            entity_type="customers.customer",
            entity_id="customer-alpha-001",
            changes={
                "fields": {
                    "name": {
                        "before": None,
                        "after": "Cliente Alpha",
                    },
                },
            },
            request_id="request-alpha-001",
            ip_address="192.0.2.10",
            user_agent="Test browser Alpha",
        )

        self.event_b = AuditEvent.objects.create(
            tenant=self.tenant_b,
            actor=self.owner_b,
            action=AuditEvent.Action.UPDATE,
            entity_type="customers.customer",
            entity_id="customer-beta-001",
            changes={
                "fields": {
                    "name": {
                        "before": "Nombre anterior",
                        "after": "Nombre nuevo",
                    },
                },
            },
        )

        self.client.force_authenticate(user=self.owner_a)

    def audit_url(self, tenant):
        return f"/api/tenants/{tenant.pk}/audit-events/"

    def event_url(self, tenant, event):
        return f"/api/tenants/{tenant.pk}/audit-events/{event.pk}/"

    def test_owner_can_list_own_audit_events(self):
        response = self.client.get(self.audit_url(self.tenant_a))

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        results = response.data["results"]
        returned_ids = {str(item["id"]) for item in results}

        self.assertIn(str(self.event_a.pk), returned_ids)
        self.assertNotIn(str(self.event_b.pk), returned_ids)

    def test_owner_cannot_list_another_tenant_audit(self):
        response = self.client.get(self.audit_url(self.tenant_b))

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_owner_cannot_retrieve_foreign_event(self):
        response = self.client.get(self.event_url(self.tenant_a, self.event_b))

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_admin_can_read_own_tenant_audit(self):
        self.client.force_authenticate(user=self.admin_a)

        response = self.client.get(self.audit_url(self.tenant_a))

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

    def test_viewer_cannot_read_audit(self):
        self.client.force_authenticate(user=self.viewer_a)

        response = self.client.get(self.audit_url(self.tenant_a))

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_user_without_membership_cannot_read_audit(self):
        outsider = User.objects.create_user(
            email="outsider@example.com",
            password="TestPassword123!",
        )

        self.client.force_authenticate(user=outsider)

        response = self.client.get(self.audit_url(self.tenant_a))

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_anonymous_user_cannot_read_audit(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.audit_url(self.tenant_a))

        self.assertIn(
            response.status_code,
            [
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_401_UNAUTHORIZED,
            ],
        )

    def test_audit_api_does_not_expose_ip_or_user_agent(self):
        response = self.client.get(self.event_url(self.tenant_a, self.event_a))

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertNotIn("ip_address", response.data)
        self.assertNotIn("user_agent", response.data)

    def test_audit_api_rejects_write_methods(self):
        list_url = self.audit_url(self.tenant_a)
        detail_url = self.event_url(self.tenant_a, self.event_a)

        responses = [
            self.client.post(list_url, {}, format="json"),
            self.client.put(detail_url, {}, format="json"),
            self.client.patch(detail_url, {}, format="json"),
            self.client.delete(detail_url),
        ]

        for response in responses:
            self.assertEqual(
                response.status_code,
                status.HTTP_405_METHOD_NOT_ALLOWED,
            )
