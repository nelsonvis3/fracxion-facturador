from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from auditlog.models import AuditEvent
from tenancy.models import Membership, Tenant

from .models import Product

User = get_user_model()


class ProductAPITests(APITestCase):
    """Pruebas de aislamiento, validación y auditoría del catálogo."""

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
            user=self.viewer_a,
            role=Membership.Role.VIEWER,
        )

        self.product_a = Product.objects.create(
            tenant=self.tenant_a,
            sku="SKU-ALPHA-001",
            name="Producto Alpha",
            description="Descripción del producto Alpha",
            unit_price=Decimal("100.00"),
            currency="ARS",
            tax_rate=Decimal("21.00"),
        )

        self.product_b = Product.objects.create(
            tenant=self.tenant_b,
            sku="SKU-BETA-001",
            name="Producto Beta",
            unit_price=Decimal("250.00"),
            currency="ARS",
            tax_rate=Decimal("10.50"),
        )

        self.client.force_authenticate(user=self.owner_a)

    def product_list_url(self, tenant):
        return f"/api/tenants/{tenant.pk}/products/"

    def product_detail_url(self, tenant, product):
        return f"/api/tenants/{tenant.pk}/products/{product.pk}/"

    def create_payload(self, **overrides):
        payload = {
            "name": "Producto Nuevo",
            "sku": "SKU-NEW-001",
            "product_type": "product",
            "unit": "unit",
            "unit_price": "125.50",
            "currency": "ARS",
            "tax_rate": "21.00",
            "is_active": True,
        }
        payload.update(overrides)
        return payload

    def test_list_only_returns_products_of_own_tenant(self):
        response = self.client.get(self.product_list_url(self.tenant_a))

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {str(item["id"]) for item in response.data["results"]}

        self.assertIn(str(self.product_a.pk), returned_ids)
        self.assertNotIn(str(self.product_b.pk), returned_ids)

    def test_cannot_access_another_tenant(self):
        response = self.client.get(self.product_list_url(self.tenant_b))

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_cannot_retrieve_foreign_product_by_id(self):
        response = self.client.get(
            self.product_detail_url(
                self.tenant_a,
                self.product_b,
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_create_ignores_spoofed_tenant(self):
        payload = self.create_payload(
            tenant=str(self.tenant_b.pk),
        )

        response = self.client.post(
            self.product_list_url(self.tenant_a),
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        product = Product.objects.get(pk=response.data["id"])

        self.assertEqual(product.tenant, self.tenant_a)

    def test_negative_price_is_rejected(self):
        response = self.client.post(
            self.product_list_url(self.tenant_a),
            self.create_payload(unit_price="-1.00"),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_tax_rate_above_one_hundred_is_rejected(self):
        response = self.client.post(
            self.product_list_url(self.tenant_a),
            self.create_payload(tax_rate="100.01"),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_duplicate_sku_is_rejected_within_tenant(self):
        response = self.client.post(
            self.product_list_url(self.tenant_a),
            self.create_payload(sku="sku-alpha-001"),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_same_sku_is_allowed_in_another_tenant(self):
        self.client.force_authenticate(user=self.owner_b)

        response = self.client.post(
            self.product_list_url(self.tenant_b),
            self.create_payload(sku="SKU-ALPHA-001"),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        product = Product.objects.get(pk=response.data["id"])

        self.assertEqual(product.tenant, self.tenant_b)
        self.assertEqual(product.sku, "SKU-ALPHA-001")

    def test_viewer_cannot_create_product(self):
        self.client.force_authenticate(user=self.viewer_a)

        response = self.client.post(
            self.product_list_url(self.tenant_a),
            self.create_payload(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_create_records_audit_event(self):
        response = self.client.post(
            self.product_list_url(self.tenant_a),
            self.create_payload(
                description="Descripción de prueba",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        event = AuditEvent.objects.get(
            tenant=self.tenant_a,
            actor=self.owner_a,
            action=AuditEvent.Action.CREATE,
            entity_type="catalog.product",
            entity_id=response.data["id"],
        )

        self.assertEqual(
            event.changes["fields"]["name"],
            "Producto Nuevo",
        )

        self.assertIn(
            "description",
            event.metadata["redacted_fields_present"],
        )

        self.assertNotIn(
            "Descripción de prueba",
            repr(event.changes),
        )

    def test_price_update_records_before_and_after_values(self):
        response = self.client.patch(
            self.product_detail_url(
                self.tenant_a,
                self.product_a,
            ),
            {"unit_price": "150.75"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )

        event = AuditEvent.objects.get(
            tenant=self.tenant_a,
            action=AuditEvent.Action.UPDATE,
            entity_type="catalog.product",
            entity_id=str(self.product_a.pk),
        )

        self.assertEqual(
            event.changes["fields"]["unit_price"],
            {
                "before": "100.00",
                "after": "150.75",
            },
        )

    def test_deactivation_records_audit_event_once(self):
        url = (
            self.product_detail_url(
                self.tenant_a,
                self.product_a,
            )
            + "deactivate/"
        )

        first_response = self.client.post(url)

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )

        second_response = self.client.post(url)

        self.assertEqual(
            second_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertFalse(Product.objects.get(pk=self.product_a.pk).is_active)

        self.assertEqual(
            AuditEvent.objects.filter(
                tenant=self.tenant_a,
                action=AuditEvent.Action.DEACTIVATE,
                entity_type="catalog.product",
                entity_id=str(self.product_a.pk),
            ).count(),
            1,
        )

    def test_physical_delete_is_not_supported(self):
        response = self.client.delete(
            self.product_detail_url(
                self.tenant_a,
                self.product_a,
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
