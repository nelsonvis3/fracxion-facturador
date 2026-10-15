from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.core.cache import cache
from django.db import connections
from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from billing.test_regressions import BillingFixtures
from catalog.models import Product
from tenancy.models import Tenant

from .models import InventoryMovement, Supplier
from .services import move_stock, save_supplier, set_inventory_policy, stock_balance


class OperationsTests(BillingFixtures, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.base = f"/api/tenants/{self.tenant.pk}"

    def policy(self):
        return set_inventory_policy(
            tenant_id=self.tenant.pk,
            actor=self.user,
            product_id=self.product.pk,
            data={"tracking": True, "minimum": "1.000"},
        )

    def move(self, kind="in", quantity="5", **kwargs):
        return move_stock(
            tenant_id=self.tenant.pk,
            actor=self.user,
            data={
                "product": str(self.product.pk),
                "kind": kind,
                "quantity": quantity,
                "reason": "Synthetic stock reconciliation",
            },
            **kwargs,
        )

    def test_supplier_edit_deactivation_uniqueness_and_history_audit(self):
        supplier = save_supplier(
            tenant_id=self.tenant.pk,
            actor=self.user,
            data={"name": "Supplier", "tax_id": "EXAMPLE-1", "notes": "never copy this free text"},
        )
        self.assertEqual(
            self.client.get(f"{self.base}/suppliers/?search=Supplier").data["count"], 1
        )
        response = self.client.patch(
            f"{self.base}/suppliers/{supplier.pk}/",
            {"is_active": False, "name": "Historical supplier"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Supplier.objects.filter(pk=supplier.pk).exists())
        self.assertEqual(
            self.client.delete(f"{self.base}/suppliers/{supplier.pk}/").status_code, 405
        )
        self.assertEqual(
            self.client.post(
                f"{self.base}/suppliers/",
                {"name": "Duplicate", "tax_id": "EXAMPLE-1"},
                format="json",
            ).status_code,
            400,
        )
        from auditlog.models import AuditEvent

        events = AuditEvent.objects.filter(entity_type="operations.supplier")
        self.assertEqual(events.count(), 2)
        self.assertTrue(all("never copy" not in str(event.changes) for event in events))

    def test_tracking_is_explicit_and_financial_documents_do_not_move_stock(self):
        self.assertEqual(
            self.client.get(f"{self.base}/inventory/items/").data["results"][0]["tracking"], False
        )
        with self.assertRaises(ValidationError):
            self.move()
        self.policy()
        self.move()
        self.issued()
        self.assertEqual(stock_balance(self.tenant, self.product), Decimal("5.000"))

    def test_in_out_adjustment_reversal_preserve_ledger_and_prevent_negative_stock(self):
        self.policy()
        incoming = self.move()
        outgoing = self.move("out", "2")
        self.assertEqual(stock_balance(self.tenant, self.product), Decimal("3.000"))
        with self.assertRaises(ValidationError):
            self.move("out", "4")
        self.move("adjustment", "-1")
        reversal = move_stock(
            tenant_id=self.tenant.pk,
            actor=self.user,
            data={"reason": "Wrong dispatch"},
            reverse_id=outgoing.pk,
            idempotency_key="reverse-stock-001",
        )
        self.assertEqual(reversal.delta, Decimal("2.000"))
        self.assertEqual(stock_balance(self.tenant, self.product), Decimal("4.000"))
        with self.assertRaises(ValidationError):
            move_stock(
                tenant_id=self.tenant.pk,
                actor=self.user,
                data={"reason": "double"},
                reverse_id=outgoing.pk,
            )
        with self.assertRaises(ValidationError):
            move_stock(
                tenant_id=self.tenant.pk,
                actor=self.user,
                data={"reason": "reverse correction"},
                reverse_id=reversal.pk,
            )
        with self.assertRaises(ValidationError):
            move_stock(
                tenant_id=self.tenant.pk,
                actor=self.user,
                data={"reason": "would go negative"},
                reverse_id=incoming.pk,
            )
        self.assertEqual(InventoryMovement.objects.count(), 4)
        from django.core.exceptions import ValidationError as ModelError

        with self.assertRaises(ModelError):
            outgoing.delete()
        with self.assertRaises(ModelError):
            outgoing.save()

    def test_idempotency_and_conflicts_are_tenant_scoped(self):
        self.policy()
        first = self.move(idempotency_key="stock-request-001")
        self.assertEqual(self.move(idempotency_key="stock-request-001").pk, first.pk)
        from billing.exceptions import IdempotencyConflict

        with self.assertRaises(IdempotencyConflict):
            self.move(quantity="4", idempotency_key="stock-request-001")
        self.assertEqual(stock_balance(self.tenant, self.product), Decimal("5.000"))

    def test_policy_unit_and_service_changes_cannot_reinterpret_historical_quantities(self):
        self.policy()
        self.move()
        self.assertEqual(
            self.client.patch(
                f"{self.base}/products/{self.product.pk}/", {"unit": "kg"}, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(
                f"{self.base}/products/{self.product.pk}/",
                {"product_type": "service"},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(
                f"{self.base}/inventory/items/{self.product.pk}/",
                {"tracking": False},
                format="json",
            ).status_code,
            400,
        )
        self.move("out", "5")
        self.assertEqual(
            self.client.patch(
                f"{self.base}/inventory/items/{self.product.pk}/",
                {"tracking": False},
                format="json",
            ).status_code,
            200,
        )

    def test_invalid_quantities_foreign_relations_and_readonly_fields_fail_safely(self):
        self.policy()
        for quantity in ["0", "NaN", "Infinity", "0.0001", "-1", "1000000000"]:
            response = self.client.post(
                f"{self.base}/inventory/movements/",
                {
                    "product": str(self.product.pk),
                    "kind": "in",
                    "quantity": quantity,
                    "reason": "validation",
                },
                format="json",
            )
            self.assertEqual(response.status_code, 400)
        other = Tenant.objects.create(name="Other inventory", slug="other-inventory")
        product = Product.objects.create(
            tenant=other, name="Foreign", unit_price="10", tax_rate="0"
        )
        response = self.client.post(
            f"{self.base}/inventory/movements/",
            {"product": str(product.pk), "kind": "in", "quantity": "2", "reason": "cross tenant"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.client.patch(
                f"{self.base}/inventory/items/{self.product.pk}/", {"balance": "999"}, format="json"
            ).status_code,
            400,
        )
        self.assertFalse(InventoryMovement.objects.exists())

    def test_low_stock_filter_alerts_and_privacy_matrix(self):
        self.policy()
        self.move("in", "2")
        self.move("out", "1")
        from automation.models import Notification

        self.assertEqual(
            Notification.objects.filter(tenant=self.tenant, title="Stock bajo").count(), 1
        )
        self.assertEqual(
            self.client.get(f"{self.base}/inventory/items/?low_stock=true").data["count"], 1
        )
        for role in ["owner", "admin", "accountant", "sales", "viewer"]:
            self.membership.role = role
            self.membership.save()
            for path in ["suppliers", "inventory/items", "inventory/movements"]:
                self.assertEqual(self.client.get(f"{self.base}/{path}/").status_code, 200)
            self.assertEqual(
                self.client.patch(
                    f"{self.base}/inventory/items/{self.product.pk}/",
                    {"minimum": "2"},
                    format="json",
                ).status_code,
                200 if role in {"owner", "admin"} else 403,
            )
        self.membership.role = "owner"
        self.membership.save()
        foreign = Tenant.objects.create(name="Foreign Ops", slug="foreign-ops")
        for path in ["suppliers", "inventory/items", "inventory/movements"]:
            self.assertEqual(self.client.get(f"/api/tenants/{foreign.pk}/{path}/").status_code, 403)
        self.membership.is_active = False
        self.membership.save()
        self.assertEqual(self.client.get(f"{self.base}/inventory/items/").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"{self.base}/inventory/items/").status_code, 401)


class ConcurrentInventory(BillingFixtures, TransactionTestCase):
    def test_two_outbound_requests_cannot_oversell(self):
        set_inventory_policy(
            tenant_id=self.tenant.pk,
            actor=self.user,
            product_id=self.product.pk,
            data={"tracking": True},
        )
        move_stock(
            tenant_id=self.tenant.pk,
            actor=self.user,
            data={
                "product": str(self.product.pk),
                "kind": "in",
                "quantity": "1",
                "reason": "opening stock",
            },
        )
        barrier = Barrier(2)

        def move(_):
            try:
                barrier.wait(timeout=10)
                move_stock(
                    tenant_id=self.tenant.pk,
                    actor=self.user,
                    data={
                        "product": str(self.product.pk),
                        "kind": "out",
                        "quantity": "1",
                        "reason": "concurrent outbound",
                    },
                )
                return "ok"
            except ValidationError:
                return "insufficient"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(move, range(2)))
        self.assertCountEqual(result, ["ok", "insufficient"])
        self.assertEqual(stock_balance(self.tenant, self.product), Decimal("0.000"))
        self.assertEqual(InventoryMovement.objects.count(), 2)
