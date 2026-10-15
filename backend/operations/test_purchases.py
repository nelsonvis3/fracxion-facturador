import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import connections
from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from auditlog.models import AuditEvent
from billing.exceptions import IdempotencyConflict
from billing.test_regressions import BillingFixtures
from tenancy.models import Membership, Tenant

from .expenses import post_expense, save_expense
from .models import (
    Expense,
    InventoryMovement,
    InventoryPolicy,
    PurchaseOrder,
    PurchaseReceipt,
    PurchaseReceiptReversal,
    Supplier,
)
from .purchases import (
    close_purchase,
    confirm_purchase,
    purchase_lines,
    receive_purchase,
    reverse_receipt,
    save_purchase,
)
from .services import move_stock, stock_balance


class PurchaseFixtures(BillingFixtures):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.product.product_type = "product"
        self.product.save()
        InventoryPolicy.objects.create(tenant=self.tenant, product=self.product)
        self.supplier = Supplier.objects.create(tenant=self.tenant, name="Synthetic supplier")
        self.base = f"/api/tenants/{self.tenant.pk}/purchases/"

    def order(self, confirmed=True, **changes):
        data = {
            "supplier": str(self.supplier.pk),
            "currency": "ARS",
            "reference": "Synthetic PO",
            "lines": [
                {
                    "product": str(self.product.pk),
                    "quantity": "5.000",
                    "unit_cost": "10.0000",
                    "tax_rate": "21.00",
                }
            ],
        }
        data.update(changes)
        order = save_purchase(tenant_id=self.tenant.pk, actor=self.user, data=data)
        if confirmed:
            confirm_purchase(tenant_id=self.tenant.pk, actor=self.user, order_id=order.pk)
        return order

    def receive(self, order, quantity="2.000", key=None):
        return receive_purchase(
            tenant_id=self.tenant.pk,
            actor=self.user,
            order_id=order.pk,
            data={
                "reference": "Synthetic receipt",
                "lines": [{"line": str(order.lines.first().pk), "quantity": quantity}],
            },
            idempotency_key=key or str(uuid.uuid4()),
        )


class PurchaseTests(PurchaseFixtures, TestCase):
    def test_multi_line_reversal_rolls_back_all_stock_when_later_line_fails(self):
        order = self.order(
            lines=[
                {
                    "product": str(self.product.pk),
                    "quantity": "2.000",
                    "unit_cost": "1.0000",
                    "tax_rate": "0.00",
                }
            ]
            * 2
        )
        receipt = receive_purchase(
            tenant_id=self.tenant.pk,
            actor=self.user,
            order_id=order.pk,
            data={
                "lines": [{"line": str(line.pk), "quantity": "2.000"} for line in order.lines.all()]
            },
        )
        move_stock(
            tenant_id=self.tenant.pk,
            actor=self.user,
            data={
                "product": str(self.product.pk),
                "kind": "out",
                "quantity": "1.000",
                "reason": "Consumed",
            },
        )
        before = InventoryMovement.objects.count()
        with self.assertRaises(ValidationError):
            reverse_receipt(
                tenant_id=self.tenant.pk,
                actor=self.user,
                receipt_id=receipt.pk,
                data={"reason": "Return both lines"},
            )
        self.assertEqual(InventoryMovement.objects.count(), before)
        self.assertEqual(stock_balance(self.tenant, self.product), 3)
        self.assertFalse(PurchaseReceiptReversal.objects.exists())
        self.assertEqual(
            [line.received_quantity for line in purchase_lines(order)],
            [Decimal("2.000"), Decimal("2.000")],
        )

    def test_decimal_totals_partial_full_receipt_and_explicit_close(self):
        order = self.order()
        self.assertEqual(order.total, Decimal("60.50"))
        self.receive(order)
        line = purchase_lines(order).get()
        self.assertEqual(
            (line.received_quantity, line.remaining_quantity), (Decimal("2"), Decimal("3"))
        )
        self.receive(order, "3.000")
        self.assertEqual(purchase_lines(order).get().remaining_quantity, 0)
        self.assertEqual(stock_balance(self.tenant, self.product), 5)
        self.assertFalse(Expense.objects.exists())
        close_purchase(
            tenant_id=self.tenant.pk,
            actor=self.user,
            order_id=order.pk,
            data={"reason": "Received in full"},
        )
        order.refresh_from_db()
        self.assertEqual(order.status, "closed")
        with self.assertRaises(ValidationError):
            self.receive(order, "1.000")

    def test_receipt_retry_conflict_and_retry_after_reversal(self):
        order = self.order()
        receipt = self.receive(order, key="synthetic-receipt-key")
        self.assertEqual(self.receive(order, key="synthetic-receipt-key").pk, receipt.pk)
        with self.assertRaises(IdempotencyConflict):
            self.receive(order, "3.000", key="synthetic-receipt-key")
        reverse_receipt(
            tenant_id=self.tenant.pk,
            actor=self.user,
            receipt_id=receipt.pk,
            data={"reason": "Wrong delivery"},
        )
        self.assertEqual(self.receive(order, key="synthetic-receipt-key").pk, receipt.pk)
        self.assertEqual(stock_balance(self.tenant, self.product), 0)
        self.assertEqual(PurchaseReceipt.objects.count(), 1)
        self.assertEqual(purchase_lines(order).get().remaining_quantity, 5)
        self.receive(order, "5.000")

    def test_excess_duplicate_and_foreign_lines_roll_back_entire_receipt(self):
        order = self.order()
        other = self.order()
        for lines in [
            [{"line": str(order.lines.first().pk), "quantity": "5.001"}],
            [{"line": str(order.lines.first().pk), "quantity": "1.000"}] * 2,
            [
                {"line": str(order.lines.first().pk), "quantity": "1.000"},
                {"line": str(other.lines.first().pk), "quantity": "1.000"},
            ],
        ]:
            with self.assertRaises(ValidationError):
                receive_purchase(
                    tenant_id=self.tenant.pk,
                    actor=self.user,
                    order_id=order.pk,
                    data={"lines": lines},
                )
        self.assertFalse(PurchaseReceipt.objects.exists())
        self.assertFalse(InventoryMovement.objects.exists())
        self.assertFalse(
            AuditEvent.objects.filter(entity_type="operations.purchasereceipt").exists()
        )

    def test_reversal_preserves_history_and_prevents_direct_stock_reversal(self):
        receipt = self.receive(self.order())
        original = receipt.lines.get().movement
        with self.assertRaises(ValidationError):
            move_stock(
                tenant_id=self.tenant.pk,
                actor=self.user,
                reverse_id=original.pk,
                data={"reason": "Bypass receipt"},
            )
        reversal = reverse_receipt(
            tenant_id=self.tenant.pk,
            actor=self.user,
            receipt_id=receipt.pk,
            data={"reason": "Returned before use"},
        )
        again = reverse_receipt(
            tenant_id=self.tenant.pk,
            actor=self.user,
            receipt_id=receipt.pk,
            data={"reason": "Retry"},
        )
        self.assertEqual(reversal.pk, again.pk)
        self.assertEqual(InventoryMovement.objects.count(), 2)
        self.assertEqual(stock_balance(self.tenant, self.product), 0)
        self.assertTrue(
            AuditEvent.objects.filter(
                entity_type="operations.purchasereceiptreversal", entity_id=str(reversal.pk)
            ).exists()
        )

    def test_reversal_after_stock_consumption_fails_without_partial_effects(self):
        receipt = self.receive(self.order())
        move_stock(
            tenant_id=self.tenant.pk,
            actor=self.user,
            data={
                "product": str(self.product.pk),
                "kind": "out",
                "quantity": "1.000",
                "reason": "Usage",
            },
        )
        with self.assertRaises(ValidationError):
            reverse_receipt(
                tenant_id=self.tenant.pk,
                actor=self.user,
                receipt_id=receipt.pk,
                data={"reason": "Return"},
            )
        self.assertEqual(stock_balance(self.tenant, self.product), 1)
        self.assertFalse(PurchaseReceiptReversal.objects.exists())
        self.assertEqual(purchase_lines(receipt.order).get().received_quantity, 2)

    def test_service_receipt_does_not_create_stock(self):
        self.product.product_type = "service"
        self.product.save()
        InventoryPolicy.objects.all().delete()
        receipt = self.receive(self.order())
        self.assertIsNone(receipt.lines.get().movement_id)
        self.assertFalse(InventoryMovement.objects.exists())

    def test_no_tracking_and_inactive_product_are_rejected(self):
        order = self.order()
        InventoryPolicy.objects.update(tracking=False)
        with self.assertRaises(ValidationError):
            self.receive(order)
        InventoryPolicy.objects.update(tracking=True)
        self.product.is_active = False
        self.product.save()
        with self.assertRaises(ValidationError):
            self.receive(order)
        self.assertFalse(PurchaseReceipt.objects.exists())

    def test_draft_edit_refreshes_lines_and_confirmed_snapshots_are_immutable(self):
        order = self.order(confirmed=False)
        self.product.name = "New catalogue name"
        self.product.save()
        confirm_purchase(tenant_id=self.tenant.pk, actor=self.user, order_id=order.pk)
        self.assertEqual(order.lines.get().product_name_snapshot, "New catalogue name")
        with self.assertRaises(ValidationError):
            save_purchase(
                tenant_id=self.tenant.pk,
                actor=self.user,
                order_id=order.pk,
                data={"reference": "Replace"},
            )
        order.refresh_from_db()
        with self.assertRaises(ModelValidationError):
            order.save()
        with self.assertRaises(ModelValidationError):
            order.lines.get().save()

    def test_cancel_without_receipts_and_close_with_partial_receipts(self):
        for quantity, expected in [(None, "cancelled"), ("1.000", "closed")]:
            order = self.order()
            receipt = self.receive(order, quantity) if quantity else None
            close_purchase(
                tenant_id=self.tenant.pk,
                actor=self.user,
                order_id=order.pk,
                data={"reason": "No more deliveries"},
            )
            order.refresh_from_db()
            self.assertEqual(order.status, expected)
            self.assertEqual(purchase_lines(order).get().remaining_quantity, 4 if quantity else 5)
            if receipt:
                with self.assertRaises(ValidationError):
                    reverse_receipt(
                        tenant_id=self.tenant.pk,
                        actor=self.user,
                        receipt_id=receipt.pk,
                        data={"reason": "Closed"},
                    )

    def test_precision_and_bounds_reject_overflow_and_unknown_fields(self):
        for changes in [
            {"currency": "BAD"},
            {"tenant": str(uuid.uuid4())},
            {"expected_on": "0001-01-01"},
            {"lines": []},
            {
                "lines": [
                    {
                        "product": str(self.product.pk),
                        "quantity": "999999999.999",
                        "unit_cost": "9999999999.9999",
                        "tax_rate": "100",
                    }
                ]
            },
        ]:
            with self.assertRaises(ValidationError):
                self.order(confirmed=False, **changes)
        self.assertFalse(PurchaseOrder.objects.exists())

    def test_link_expense_requires_same_tenant_supplier_currency_and_confirmed_order(self):
        order = self.order()
        payload = {
            "supplier": str(self.supplier.pk),
            "purchase_order": str(order.pk),
            "description": "Supplier charge",
            "currency": "ARS",
            "net_amount": "50.00",
            "tax_rate": "21.00",
            "incurred_on": "2026-10-15",
        }
        expense = save_expense(tenant_id=self.tenant.pk, actor=self.user, data=payload)
        self.assertEqual(expense.purchase_order_id, order.pk)
        post_expense(tenant_id=self.tenant.pk, actor=self.user, expense_id=expense.pk)
        for changes in [
            {"currency": "USD"},
            {"supplier": None},
            {"purchase_order": str(uuid.uuid4())},
            {"purchase_order": str(self.order(confirmed=False).pk)},
        ]:
            with self.assertRaises(ValidationError):
                save_expense(tenant_id=self.tenant.pk, actor=self.user, data=payload | changes)

    def test_active_company_and_role_are_rechecked_by_services(self):
        order = self.order()
        for role in ["viewer", "sales", "accountant"]:
            self.membership.role = role
            self.membership.save()
            with self.assertRaises(PermissionDenied):
                self.receive(order)
        self.membership.role = "owner"
        self.membership.is_active = False
        self.membership.save()
        with self.assertRaises(PermissionDenied):
            self.receive(order)

    def test_api_authorization_matrix_and_cross_company_identifiers(self):
        order = self.order()
        receipt = self.receive(order)
        client = APIClient()
        reads = [
            self.base,
            f"{self.base}{order.pk}/",
            f"{self.base}{order.pk}/lines/",
            f"{self.base}{order.pk}/receipts/",
        ]
        writes = [
            ("post", self.base),
            ("patch", f"{self.base}{order.pk}/"),
            ("post", f"{self.base}{order.pk}/confirm/"),
            ("post", f"{self.base}{order.pk}/close/"),
            ("post", f"{self.base}{order.pk}/receipts/"),
            ("post", f"/api/tenants/{self.tenant.pk}/purchase-receipts/{receipt.pk}/reverse/"),
        ]
        for method, path in [("get", p) for p in reads] + writes:
            self.assertEqual(getattr(client, method)(path, {}, format="json").status_code, 401)
        outsider = get_user_model().objects.create_user(email="outsider-purchasing@example.com")
        client.force_authenticate(outsider)
        for method, path in [("get", p) for p in reads] + writes:
            self.assertEqual(getattr(client, method)(path, {}, format="json").status_code, 403)
        client.force_authenticate(self.user)
        for role in ["viewer", "sales", "accountant", "owner", "admin"]:
            self.membership.role = role
            self.membership.save()
            for path in reads:
                self.assertEqual(
                    client.get(path).status_code,
                    200 if role in {"accountant", "owner", "admin"} else 403,
                    (role, path),
                )
            if role not in {"owner", "admin"}:
                for method, path in writes:
                    self.assertEqual(
                        getattr(client, method)(path, {}, format="json").status_code,
                        403,
                        (role, path),
                    )
        self.membership.is_active = False
        self.membership.save()
        for method, path in [("get", p) for p in reads] + writes:
            self.assertEqual(getattr(client, method)(path, {}, format="json").status_code, 403)
        self.membership.is_active = True
        self.membership.save()
        self.tenant.is_active = False
        self.tenant.save()
        for method, path in [("get", p) for p in reads] + writes:
            self.assertEqual(getattr(client, method)(path, {}, format="json").status_code, 403)
        self.tenant.is_active = True
        self.tenant.save()
        other = Tenant.objects.create(name="Other", slug="other-purchase")
        Membership.objects.create(tenant=other, user=self.user, role="owner")
        foreign_base = f"/api/tenants/{other.pk}"
        for method, path in [("get", p) for p in reads[1:]] + writes[1:]:
            path = path.replace(f"/api/tenants/{self.tenant.pk}", foreign_base)
            self.assertEqual(
                getattr(client, method)(path, {}, format="json").status_code, 404, path
            )
        self.assertEqual(
            client.post(
                f"{foreign_base}/purchases/",
                {
                    "supplier": str(self.supplier.pk),
                    "currency": "ARS",
                    "lines": [
                        {
                            "product": str(self.product.pk),
                            "quantity": "1",
                            "unit_cost": "1",
                            "tax_rate": "0",
                        }
                    ],
                },
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(client.post(f"{self.base}{order.pk}/", {}, format="json").status_code, 405)

    def test_catalog_cannot_reinterpret_open_purchase_units(self):
        self.order()
        client = APIClient()
        client.force_authenticate(self.user)
        for changes in [{"unit": "kg"}, {"product_type": "service"}]:
            response = client.patch(
                f"/api/tenants/{self.tenant.pk}/products/{self.product.pk}/", changes, format="json"
            )
            self.assertEqual(response.status_code, 400)


class PurchaseConcurrencyTests(PurchaseFixtures, TransactionTestCase):
    def test_two_receipts_cannot_exceed_ordered_quantity(self):
        order = self.order()
        barrier = Barrier(2)

        def work():
            try:
                barrier.wait(timeout=10)
                self.receive(order, "4.000")
                return "received"
            except ValidationError:
                return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: work(), range(2)))
        self.assertCountEqual(results, ["received", "rejected"])
        self.assertEqual(stock_balance(self.tenant, self.product), 4)
        self.assertEqual(purchase_lines(order).get().received_quantity, 4)

    def test_identical_concurrent_requests_have_one_receipt_and_one_stock_effect(self):
        order = self.order()
        barrier = Barrier(2)

        def work():
            try:
                barrier.wait(timeout=10)
                return self.receive(order, key="simultaneous-receipt").pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: work(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(stock_balance(self.tenant, self.product), 2)
        self.assertEqual(InventoryMovement.objects.count(), 1)
