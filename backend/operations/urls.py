from rest_framework.routers import SimpleRouter

from .expense_views import CategoryViewSet, ExpensePaymentViewSet, ExpenseViewSet
from .purchase_views import PurchaseReceiptViewSet, PurchaseViewSet
from .views import InventoryItemViewSet, InventoryMovementViewSet, SupplierViewSet

router = SimpleRouter()
router.register("suppliers", SupplierViewSet, basename="suppliers")
router.register("inventory/items", InventoryItemViewSet, basename="inventory-items")
router.register("inventory/movements", InventoryMovementViewSet, basename="inventory-movements")
router.register("expenses/categories", CategoryViewSet, basename="expense-categories")
router.register("expenses", ExpenseViewSet, basename="expenses")
router.register("expense-payments", ExpensePaymentViewSet, basename="expense-payments")
router.register("purchases", PurchaseViewSet, basename="purchases")
router.register("purchase-receipts", PurchaseReceiptViewSet, basename="purchase-receipts")
urlpatterns = router.urls
