from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import BusinessSettingsView, CompanyLogoView, InvitationViewSet, MembershipViewSet

router = SimpleRouter()
router.register("members", MembershipViewSet, basename="members")
router.register("invitations", InvitationViewSet, basename="invitations")

urlpatterns = [
    path("settings/", BusinessSettingsView.as_view(), name="business-settings"),
    path("settings/logo/", CompanyLogoView.as_view(), name="company-logo"),
    *router.urls,
]
