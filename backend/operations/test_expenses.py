import base64
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from io import BytesIO
from threading import Barrier
from unittest.mock import patch

from django.core.cache import cache
from django.db import connections
from django.test import TestCase, TransactionTestCase
from PIL import Image
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from billing.test_regressions import BillingFixtures
from tenancy.models import Tenant

from .expenses import (
    expense_query,
    paid_amount,
    pay_expense,
    post_expense,
    reverse_expense_payment,
    save_category,
    save_expense,
    void_expense,
)
from .models import Expense, ExpensePayment, ExpensePaymentReversal, InventoryMovement, Supplier


class ExpenseFixtures(BillingFixtures):
    def draft_expense(self, **extra):
        return save_expense(
            tenant_id=self.tenant.pk,
            actor=self.user,
            data={
                "description": "Synthetic vendor obligation",
                "incurred_on": "2026-10-14",
                "currency": "ARS",
                "net_amount": "100.00",
                "tax_rate": "21.00",
                **extra,
            },
        )

    def posted_expense(self, **extra):
        return post_expense(
            tenant_id=self.tenant.pk, actor=self.user, expense_id=self.draft_expense(**extra).pk
        )

    def pay(self, expense, amount="40", **extra):
        return pay_expense(
            tenant_id=self.tenant.pk,
            actor=self.user,
            expense_id=expense.pk,
            data={"amount": amount, "method": "cash"},
            **extra,
        )


class ExpenseTests(ExpenseFixtures, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.base = f"/api/tenants/{self.tenant.pk}"

    def test_explicit_tax_rounding_snapshots_and_immutable_posted_document(self):
        supplier = Supplier.objects.create(tenant=self.tenant, name="Historical vendor")
        category = save_category(
            tenant_id=self.tenant.pk, actor=self.user, data={"name": "Professional services"}
        )
        expense = self.posted_expense(
            supplier=str(supplier.pk),
            category=str(category.pk),
            net_amount="0.03",
            tax_rate="50.00",
        )
        self.assertEqual(expense.tax_amount, Decimal("0.02"))
        self.assertEqual(expense.total, Decimal("0.05"))
        supplier.name = "Renamed vendor"
        supplier.save()
        self.assertEqual(expense.supplier_name_snapshot, "Historical vendor")
        self.assertEqual(
            self.client.patch(
                f"{self.base}/expenses/{expense.pk}/", {"net_amount": "999"}, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(f"{self.base}/expenses/{expense.pk}/", {}, format="json").status_code,
            405,
        )
        self.assertEqual(self.client.delete(f"{self.base}/expenses/{expense.pk}/").status_code, 405)
        self.assertFalse(InventoryMovement.objects.exists())

    def test_partial_full_payment_reversal_and_idempotency_keep_balances_correct(self):
        expense = self.posted_expense()
        payment = self.pay(expense, idempotency_key="expense-payment-001")
        self.assertEqual(self.pay(expense, idempotency_key="expense-payment-001").pk, payment.pk)
        self.pay(expense, "81.00")
        self.assertEqual(paid_amount(self.tenant, expense), Decimal("121.00"))
        with self.assertRaises(ValidationError):
            self.pay(expense, "0.01")
        reverse_expense_payment(
            tenant_id=self.tenant.pk,
            actor=self.user,
            payment_id=payment.pk,
            data={"reason": "Wrong payment"},
        )
        reverse_expense_payment(
            tenant_id=self.tenant.pk,
            actor=self.user,
            payment_id=payment.pk,
            data={"reason": "Retry same effect"},
        )
        row = expense_query(self.tenant).get(pk=expense.pk)
        self.assertEqual(row.balance, Decimal("40.00"))
        self.assertEqual(ExpensePaymentReversal.objects.count(), 1)
        # Retrying an already reversed request does not pay the expense again.
        self.assertEqual(self.pay(expense, idempotency_key="expense-payment-001").pk, payment.pk)
        self.assertEqual(ExpensePayment.objects.count(), 2)

    def test_payments_require_registered_obligation_and_void_requires_no_effective_payments(self):
        draft = self.draft_expense()
        with self.assertRaises(ValidationError):
            self.pay(draft)
        expense = post_expense(tenant_id=self.tenant.pk, actor=self.user, expense_id=draft.pk)
        payment = self.pay(expense)
        with self.assertRaises(ValidationError):
            void_expense(
                tenant_id=self.tenant.pk,
                actor=self.user,
                expense_id=expense.pk,
                data={"reason": "duplicate"},
            )
        reverse_expense_payment(
            tenant_id=self.tenant.pk,
            actor=self.user,
            payment_id=payment.pk,
            data={"reason": "correct before void"},
        )
        void_expense(
            tenant_id=self.tenant.pk,
            actor=self.user,
            expense_id=expense.pk,
            data={"reason": "duplicate"},
        )
        expense.refresh_from_db()
        self.assertEqual(expense.status, "void")
        self.assertTrue(ExpensePayment.objects.filter(pk=payment.pk).exists())
        with self.assertRaises(ValidationError):
            post_expense(tenant_id=self.tenant.pk, actor=self.user, expense_id=expense.pk)

    def test_invalid_values_foreign_relations_and_images_fail_without_partial_records(self):
        other = Tenant.objects.create(name="Foreign expense", slug="foreign-expense")
        supplier = Supplier.objects.create(tenant=other, name="Private supplier")
        for extra in [
            {"supplier": str(supplier.pk)},
            {"net_amount": "NaN"},
            {"net_amount": "0"},
            {"net_amount": "0.001"},
            {"tax_rate": "101"},
            {"currency": "ZZZ"},
            {"due_date": "2026-01-01"},
            {"attachment_data": base64.b64encode(b"<svg onload='attack()'/>").decode()},
        ]:
            with self.assertRaises(ValidationError):
                self.draft_expense(**extra)
        self.assertFalse(Expense.objects.exists())

    def test_private_image_is_recoded_and_attachment_requires_finance_authorization(self):
        stream = BytesIO()
        Image.new("RGB", (40, 40), "red").save(stream, format="PNG")
        expense = self.posted_expense(
            attachment_data=base64.b64encode(
                stream.getvalue() + b"SYNTHETIC_TRAILING_CONTENT"
            ).decode()
        )
        url = f"{self.base}/expenses/{expense.pk}/attachment/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"SYNTHETIC_TRAILING", response.content)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("attachment", response["Content-Disposition"])
        self.membership.role = "viewer"
        self.membership.save()
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_all_new_expense_routes_enforce_finance_roles_and_tenant_state(self):
        expense = self.posted_expense()
        for role in ["owner", "admin", "accountant", "sales", "viewer"]:
            self.membership.role = role
            self.membership.save()
            for route in ["expenses/", "expenses/categories/", f"expenses/{expense.pk}/payments/"]:
                self.assertEqual(
                    self.client.get(f"{self.base}/{route}").status_code,
                    200 if role in {"owner", "admin", "accountant"} else 403,
                )
        self.membership.role = "owner"
        self.membership.save()
        other = Tenant.objects.create(name="Other financial data", slug="other-financial-data")
        self.assertEqual(self.client.get(f"/api/tenants/{other.pk}/expenses/").status_code, 403)
        self.membership.is_active = False
        self.membership.save()
        self.assertEqual(self.client.get(f"{self.base}/expenses/").status_code, 403)
        self.membership.is_active = True
        self.membership.save()
        Tenant.objects.filter(pk=self.tenant.pk).update(is_active=False)
        self.assertEqual(self.client.get(f"{self.base}/expenses/").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"{self.base}/expenses/").status_code, 401)

    def test_payment_and_post_rollback_if_audit_fails(self):
        expense = self.draft_expense()
        with patch(
            "operations.expenses.record_audit_event",
            side_effect=RuntimeError("synthetic audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                post_expense(tenant_id=self.tenant.pk, actor=self.user, expense_id=expense.pk)
        expense.refresh_from_db()
        self.assertEqual(expense.status, "draft")
        post_expense(tenant_id=self.tenant.pk, actor=self.user, expense_id=expense.pk)
        with patch(
            "operations.expenses.record_audit_event",
            side_effect=RuntimeError("synthetic audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.pay(expense)
        self.assertFalse(ExpensePayment.objects.exists())


class ConcurrentExpenseTests(ExpenseFixtures, TransactionTestCase):
    def test_two_payments_cannot_exceed_outstanding_amount(self):
        expense = self.posted_expense()
        barrier = Barrier(2)

        def pay(_):
            try:
                barrier.wait(timeout=10)
                self.pay(expense, "100.00")
                return "ok"
            except ValidationError:
                return "excess"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(pay, range(2)))
        self.assertCountEqual(result, ["ok", "excess"])
        self.assertEqual(paid_amount(self.tenant, expense), Decimal("100.00"))
