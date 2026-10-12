from django.urls import path

from .password_reset import (
    password_reset_confirm_view,
    password_reset_request_view,
)
from .views import (
    csrf_token_view,
    current_user_view,
    login_view,
    logout_view,
    my_tenants,
    register_view,
)

urlpatterns = [
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
