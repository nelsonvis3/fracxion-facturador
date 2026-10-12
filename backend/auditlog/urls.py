from rest_framework.routers import SimpleRouter

from .views import AuditEventViewSet

router = SimpleRouter()

router.register(
    "audit-events",
    AuditEventViewSet,
    basename="tenant-audit-events",
)

urlpatterns = router.urls
