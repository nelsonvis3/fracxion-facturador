from rest_framework.routers import SimpleRouter

from .views import JobViewSet, NotificationViewSet, RuleViewSet

router = SimpleRouter()
router.register("automation/rules", RuleViewSet, basename="automation-rules")
router.register("reports/jobs", JobViewSet, basename="report-jobs")
router.register("notifications", NotificationViewSet, basename="notifications")
urlpatterns = router.urls
