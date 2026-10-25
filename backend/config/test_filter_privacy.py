import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from billing.test_regressions import BillingFixtures
from operations.models import ExpenseCategory, Supplier
from tenancy.models import Membership, Tenant


class RelatedFilterPrivacyTests(BillingFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.other = Tenant.objects.create(name="Empty company", slug="empty-filter-company")
        Membership.objects.create(tenant=self.other, user=self.user, role="owner")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def assert_private_filter(self, resource, field, foreign_id):
        responses = [
            self.client.get(f"/api/tenants/{self.other.pk}/{resource}/", {field: str(key)})
            for key in [foreign_id, uuid.uuid4()]
        ]
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual([response.data["count"] for response in responses], [0, 0])
        self.assertEqual(responses[0].data, responses[1].data)

    def test_payment_invoice_filter_has_no_global_existence_oracle(self):
        invoice = self.issued()
        self.assert_private_filter("payments", "invoice", invoice.pk)

    def test_operations_related_filters_have_no_global_existence_oracle(self):
        supplier = Supplier.objects.create(tenant=self.tenant, name="Private supplier")
        category = ExpenseCategory.objects.create(tenant=self.tenant, name="Private category")
        for resource, field, foreign_id in [
            ("purchases", "supplier", supplier.pk),
            ("expenses", "supplier", supplier.pk),
            ("expenses", "category", category.pk),
            ("inventory/movements", "product", self.product.pk),
        ]:
            self.assert_private_filter(resource, field, foreign_id)
