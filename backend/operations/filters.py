from django_filters import rest_framework as filters

from .models import Expense, InventoryMovement, PurchaseOrder


class ExpenseFilter(filters.FilterSet):
    # UUID filters avoid a global ModelChoice lookup that would distinguish an
    # existing foreign tenant's UUID from a nonexistent UUID in list responses.
    supplier = filters.UUIDFilter()
    category = filters.UUIDFilter()
    purchase_order = filters.UUIDFilter()

    class Meta:
        model = Expense
        fields = ["currency", "supplier", "category", "status", "purchase_order"]


class PurchaseFilter(filters.FilterSet):
    supplier = filters.UUIDFilter()

    class Meta:
        model = PurchaseOrder
        fields = ["status", "supplier", "currency"]


class MovementFilter(filters.FilterSet):
    product = filters.UUIDFilter()

    class Meta:
        model = InventoryMovement
        fields = ["product", "kind"]
