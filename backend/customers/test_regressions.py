from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from tenancy.models import Membership, Tenant

from .models import Customer


class CustomerRegressionTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="customer-regression@example.com")
        self.tenant = Tenant.objects.create(name="Customers", slug="customers")
        Membership.objects.create(user=self.user, tenant=self.tenant, role="owner")
        self.client.force_authenticate(self.user)
        self.url = f"/api/tenants/{self.tenant.pk}/customers/"

    def create(self, **kwargs):
        return self.client.post(self.url, {"name": "Customer", **kwargs}, format="json")

    def test_rejects_letters_and_unicode_digits_in_documents(self):
        for number in ["abc30123456", "３０１２３４５６"]:
            response = self.create(document_type="dni", document_number=number)
            self.assertEqual(response.status_code, 400)

    def test_accepts_province_iso_code(self):
        response = self.create(province="AR-P")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["province"], "Formosa")

    def test_country_change_revalidates_existing_province_and_postal(self):
        customer = self.create(province="Formosa", postal_code="3600").data
        response = self.client.patch(
            self.url + customer["id"] + "/", {"country_code": "US"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("province", response.data)
        self.assertIn("postal_code", response.data)

    def test_unrelated_patch_preserves_legacy_document(self):
        customer = Customer.objects.create(
            tenant=self.tenant, name="Legacy", document_type="dni", document_number="123"
        )
        response = self.client.patch(
            self.url + str(customer.pk) + "/", {"name": "Edited"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        customer.refresh_from_db()
        self.assertEqual(customer.document_number, "123")

    def test_postal_patterns_by_country(self):
        for country, valid, invalid in [
            ("US", "90210", "3600"),
            ("BR", "01001-000", "ABC"),
            ("CA", "K1A 0B1", "90210"),
            ("DE", "10115", "1011"),
        ]:
            with self.subTest(country=country):
                self.assertEqual(
                    self.create(country_code=country, postal_code=valid).status_code, 201
                )
                self.assertEqual(
                    self.create(country_code=country, postal_code=invalid).status_code, 400
                )

    def test_address_controls_rejected(self):
        response = self.create(address="Calle\n123")
        self.assertEqual(response.status_code, 400)

    def test_reactivation_and_filters(self):
        customer = self.create().data
        detail = self.url + customer["id"] + "/"
        self.assertEqual(
            self.client.post(detail + "deactivate/", {}, format="json").status_code, 200
        )
        self.assertEqual(self.client.get(self.url, {"is_active": "true"}).data["count"], 0)
        self.assertEqual(
            self.client.patch(detail, {"is_active": True}, format="json").status_code, 200
        )
        self.assertEqual(self.client.get(self.url, {"is_active": "true"}).data["count"], 1)
