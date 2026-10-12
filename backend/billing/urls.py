from rest_framework.routers import SimpleRouter

from .views import InvoiceViewSet, PaymentViewSet

router = SimpleRouter()

router.register(
    "invoices",
    InvoiceViewSet,
    basename="tenant-invoices",
)

router.register(
    "payments",
    PaymentViewSet,
    basename="tenant-payments",
)

urlpatterns = router.urls
