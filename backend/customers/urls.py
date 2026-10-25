from rest_framework.routers import SimpleRouter

from .views import CustomerViewSet

router = SimpleRouter()
router.register(
    "customers",
    CustomerViewSet,
    basename="tenant-customers",
)

urlpatterns = router.urls
