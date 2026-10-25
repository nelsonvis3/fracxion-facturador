from django.urls import path
from rest_framework.routers import SimpleRouter

from tenancy.views import InvitationAcceptView, InvitationPreviewView

from .email_verification import (
    VerificationConfirmView,
    VerificationRequestView,
    VerificationStatusView,
)
from .mfa_views import MFAManageView, MFAStatusView, mfa_login_view
from .password_reset import (
    password_reset_confirm_view,
    password_reset_request_view,
)
from .session_views import AccountSessionViewSet, ChangePasswordView
from .views import (
    csrf_token_view,
    current_user_view,
    login_view,
    logout_view,
    my_tenants,
    register_view,
)

router = SimpleRouter()
router.register("sessions", AccountSessionViewSet, basename="account-sessions")
urlpatterns = [
    path("mfa/", MFAStatusView.as_view(), name="mfa-status"),
    path("mfa/manage/", MFAManageView.as_view(), name="mfa-manage"),
    path("mfa/login/", mfa_login_view, name="mfa-login"),
    path("email-verification/", VerificationStatusView.as_view(), name="email-verification-status"),
    path(
        "email-verification/request/",
        VerificationRequestView.as_view(),
        name="email-verification-request",
    ),
    path(
        "email-verification/confirm/",
        VerificationConfirmView.as_view(),
        name="email-verification-confirm",
    ),
    path("password/change/", ChangePasswordView.as_view(), name="password-change"),
    *router.urls,
    path("invitations/preview/", InvitationPreviewView.as_view(), name="invitation-preview"),
    path("invitations/accept/", InvitationAcceptView.as_view(), name="invitation-accept"),
    # Sesión y autenticación
    path("csrf/", csrf_token_view, name="auth-csrf"),
    path("register/", register_view, name="auth-register"),
    path("login/", login_view, name="auth-login"),
    path("logout/", logout_view, name="auth-logout"),
    path("me/", current_user_view, name="auth-me"),
    # Recuperación de contraseña
    path(
        "password-reset/",
        password_reset_request_view,
        name="password-reset-request",
    ),
    path(
        "password-reset/confirm/",
        password_reset_confirm_view,
        name="password-reset-confirm",
    ),
    path("tenants/", my_tenants, name="my-tenants"),
]
