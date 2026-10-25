from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APITestCase

from auditlog.models import AuditEvent
from tenancy.models import Membership, Tenant

from .models import Customer

User = get_user_model()


class CustomerAPISecurityTests(APITestCase):
    """Comprueba el aislamiento multi-tenant de la API."""

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

        self.customer_a = Customer.objects.create(
            tenant=self.tenant_a,
            name="Cliente Alpha",
            document_type=Customer.DocumentType.CUIT,
            document_number="20301234567",
            created_by=self.owner_a,
        )

        self.customer_b = Customer.objects.create(
            tenant=self.tenant_b,
            name="Cliente Beta",
            document_type=Customer.DocumentType.CUIT,
            document_number="27345678901",
            created_by=self.owner_b,
        )

        self.client.force_authenticate(user=self.owner_a)

    def tenant_url(self, tenant):
        return f"/api/tenants/{tenant.pk}/customers/"

    def customer_url(self, tenant, customer):
        return f"/api/tenants/{tenant.pk}/customers/{customer.pk}/"

    def test_list_only_returns_customers_of_own_tenant(self):
        response = self.client.get(self.tenant_url(self.tenant_a))

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        results = response.data["results"]
        returned_ids = {str(item["id"]) for item in results}

        self.assertIn(str(self.customer_a.pk), returned_ids)
        self.assertNotIn(str(self.customer_b.pk), returned_ids)

    def test_cannot_access_another_tenant(self):
        response = self.client.get(self.tenant_url(self.tenant_b))

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_cannot_retrieve_foreign_customer_by_id(self):
        response = self.client.get(
            self.customer_url(
                self.tenant_a,
                self.customer_b,
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_create_ignores_spoofed_tenant_and_creator(self):
        payload = {
            "tenant": str(self.tenant_b.pk),
            "created_by": self.owner_b.pk,
            "name": "Cliente Nuevo",
            "customer_type": "individual",
            "document_type": "dni",
            "document_number": "12345678",
            "email": "cliente@example.com",
        }

        response = self.client.post(
            self.tenant_url(self.tenant_a),
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        customer = Customer.objects.get(pk=response.data["id"])

        self.assertEqual(customer.tenant, self.tenant_a)
        self.assertEqual(customer.created_by, self.owner_a)

    def test_viewer_cannot_create_customer(self):
        self.client.force_authenticate(
            user=self.viewer_a,
        )

        payload = {
            "name": "Cliente no autorizado",
            "customer_type": "individual",
        }

        response = self.client.post(
            self.tenant_url(self.tenant_a),
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_user_without_membership_is_denied(self):
        outsider = User.objects.create_user(
            email="outsider@example.com",
            password="TestPassword123!",
        )

        self.client.force_authenticate(user=outsider)

        response = self.client.get(self.tenant_url(self.tenant_a))

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_duplicate_document_is_rejected_within_tenant(self):
        payload = {
            "name": "Cliente Duplicado",
            "customer_type": "individual",
            "document_type": "cuit",
            "document_number": "20-30123456-7",
        }

        response = self.client.post(
            self.tenant_url(self.tenant_a),
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_same_document_is_allowed_in_another_tenant(self):
        self.client.force_authenticate(
            user=self.owner_b,
        )

        payload = {
            "name": "Otro registro del mismo documento",
            "customer_type": "individual",
            "document_type": "cuit",
            "document_number": "20-30123456-3",
        }

        response = self.client.post(
            self.tenant_url(self.tenant_b),
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

    def test_delete_method_is_not_supported(self):
        response = self.client.delete(
            self.customer_url(
                self.tenant_a,
                self.customer_a,
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_owner_can_deactivate_customer(self):
        response = self.client.post(
            self.customer_url(
                self.tenant_a,
                self.customer_a,
            )
            + "deactivate/",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.customer_a.refresh_from_db()

        self.assertFalse(self.customer_a.is_active)

    def test_create_customer_records_audit_event(self):
        payload = {
            "name": "Cliente Auditado",
            "customer_type": "individual",
            "email": "auditado@example.com",
            "notes": "NOTA_PRIVADA_NO_REGISTRAR",
        }

        response = self.client.post(
            self.tenant_url(self.tenant_a),
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        event = AuditEvent.objects.get(
            tenant=self.tenant_a,
            action=AuditEvent.Action.CREATE,
            entity_type="customers.customer",
            entity_id=response.data["id"],
        )

        self.assertEqual(event.actor, self.owner_a)
        self.assertEqual(
            event.changes["fields"]["name"],
            "Cliente Auditado",
        )

        audit_content = repr(
            {
                "changes": event.changes,
                "metadata": event.metadata,
            }
        )

        self.assertNotIn(
            "NOTA_PRIVADA_NO_REGISTRAR",
            audit_content,
        )

    def test_update_records_before_and_after_values(self):
        response = self.client.patch(
            self.customer_url(
                self.tenant_a,
                self.customer_a,
            ),
            {
                "name": "Cliente Alpha Actualizado",
                "notes": "OTRA_NOTA_PRIVADA",
            },
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
            entity_type="customers.customer",
            entity_id=str(self.customer_a.pk),
        )

        name_change = event.changes["fields"]["name"]

        self.assertEqual(
            name_change["before"],
            "Cliente Alpha",
        )
        self.assertEqual(
            name_change["after"],
            "Cliente Alpha Actualizado",
        )

        self.assertIn(
            "notes",
            event.metadata["redacted_fields_changed"],
        )

        self.assertNotIn(
            "OTRA_NOTA_PRIVADA",
            repr(
                {
                    "changes": event.changes,
                    "metadata": event.metadata,
                }
            ),
        )

    def test_deactivation_records_audit_event(self):
        response = self.client.post(
            self.customer_url(
                self.tenant_a,
                self.customer_a,
            )
            + "deactivate/",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        event = AuditEvent.objects.get(
            tenant=self.tenant_a,
            action=AuditEvent.Action.DEACTIVATE,
            entity_type="customers.customer",
            entity_id=str(self.customer_a.pk),
        )

        self.assertEqual(
            event.changes["fields"]["is_active"],
            {
                "before": True,
                "after": False,
            },
        )

        # Repetir la operación no debe duplicar el evento.
        response = self.client.post(
            self.customer_url(
                self.tenant_a,
                self.customer_a,
            )
            + "deactivate/",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            AuditEvent.objects.filter(
                tenant=self.tenant_a,
                action=AuditEvent.Action.DEACTIVATE,
                entity_id=str(self.customer_a.pk),
            ).count(),
            1,
        )

    def test_audit_failure_rolls_back_customer_creation(self):
        payload = {
            "name": "Cliente Sin Auditoría",
            "customer_type": "individual",
        }

        with patch(
            "customers.views.record_audit_event",
            side_effect=RuntimeError("Auditoría no disponible"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    self.tenant_url(self.tenant_a),
                    payload,
                    format="json",
                )

        self.assertFalse(
            Customer.objects.filter(
                tenant=self.tenant_a,
                name="Cliente Sin Auditoría",
            ).exists()
        )

    def test_audit_events_cannot_be_updated_or_deleted_by_instance(self):
        response = self.client.post(
            self.tenant_url(self.tenant_a),
            {
                "name": "Cliente con Evento Inmutable",
                "customer_type": "individual",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        event = AuditEvent.objects.get(
            entity_type="customers.customer",
            entity_id=response.data["id"],
            action=AuditEvent.Action.CREATE,
        )

        event.action = AuditEvent.Action.UPDATE

        with self.assertRaises(ValidationError):
            event.save()

        with self.assertRaises(ValidationError):
            event.delete()


class CustomerValidationAPITests(APITestCase):
    """Comprueba las validaciones de los datos de clientes."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Empresa Validaciones",
            slug="empresa-validaciones",
        )

        self.user = User.objects.create_user(
            email="validaciones@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=Membership.Role.OWNER,
        )

        self.client.force_authenticate(user=self.user)

        self.url = f"/api/tenants/{self.tenant.pk}/customers/"

    def payload(self, **overrides):
        data = {
            "name": "Cliente de validación",
            "customer_type": "individual",
            "country_code": "AR",
        }
        data.update(overrides)
        return data

    def create_customer(self, **overrides):
        return self.client.post(
            self.url,
            self.payload(**overrides),
            format="json",
        )

    def test_rejects_invalid_email(self):
        response = self.create_customer(email="correo-invalido")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_rejects_phone_with_letters(self):
        response = self.create_customer(phone="abc1234567")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)

    def test_rejects_phone_with_too_few_digits(self):
        response = self.create_customer(phone="123456")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)

    def test_accepts_phone_with_common_separators(self):
        response = self.create_customer(phone="+54 11 2345-6789")

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

    def test_rejects_invalid_argentine_postal_code(self):
        response = self.create_customer(postal_code="ABC")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("postal_code", response.data)

    def test_accepts_traditional_argentine_postal_code(self):
        response = self.create_customer(postal_code="3600")

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

    def test_accepts_argentine_cpa_format(self):
        response = self.create_customer(postal_code="C1425ABC")

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

    def test_rejects_dni_with_too_few_digits(self):
        response = self.create_customer(
            document_type="dni",
            document_number="123456",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("document_number", response.data)

    def test_accepts_dni_with_valid_length(self):
        response = self.create_customer(
            document_type="dni",
            document_number="30123456",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

    def test_rejects_cuit_with_invalid_check_digit(self):
        response = self.create_customer(
            document_type="cuit",
            document_number="20-30123456-7",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("document_number", response.data)

    def test_accepts_cuit_with_valid_check_digit(self):
        response = self.create_customer(
            document_type="cuit",
            document_number="20-30123456-3",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        self.assertEqual(response.data["document_number"], "20301234563")

    def test_document_type_and_number_must_be_paired(self):
        response = self.create_customer(document_type="dni")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("document_number", response.data)

        response = self.create_customer(document_number="30123456")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("document_number", response.data)

    def test_rejects_duplicate_document_inside_same_tenant(self):
        payload = {
            "document_type": "cuit",
            "document_number": "20301234563",
        }

        first_response = self.create_customer(**payload)

        self.assertEqual(
            first_response.status_code,
            status.HTTP_201_CREATED,
            first_response.data,
        )

        second_response = self.create_customer(
            name="Otro cliente",
            **payload,
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("document_number", second_response.data)

    def test_rejects_country_code_with_wrong_length(self):
        response = self.create_customer(country_code="ARG")

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("country_code", response.data)

    def test_rejects_unknown_country_code(self):
        response = self.create_customer(country_code="ZZ")

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("country_code", response.data)

    def test_accepts_iso_country_code(self):
        response = self.create_customer(country_code="US")

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )
        self.assertEqual(response.data["country_code"], "US")

    def test_rejects_unknown_argentine_province(self):
        response = self.create_customer(province="Atlantis")

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("province", response.data)

    def test_normalizes_argentine_province(self):
        response = self.create_customer(province="formosa")

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )
        self.assertEqual(response.data["province"], "Formosa")

    def test_rejects_province_from_another_country(self):
        response = self.create_customer(
            country_code="US",
            province="Formosa",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("province", response.data)

    def test_accepts_known_us_state(self):
        response = self.create_customer(
            country_code="US",
            province="California",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )
        self.assertEqual(response.data["province"], "California")
