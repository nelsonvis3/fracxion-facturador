from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, logout
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.parsers import parse_json_body
from config.schema import TenantListSerializer
from tenancy.models import Membership

from .rate_limits import is_rate_limited, rate_limit_response
from .registration import REGISTRATION_LIMIT, register_account
from .security import security_event
from .signup_code import confirm_code, send_new_code


def serialize_user(user):
    """Expone únicamente los datos básicos necesarios del usuario."""

    return {
        "id": str(user.pk),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


@require_GET
@ensure_csrf_cookie
@never_cache
def csrf_token_view(request):
    """Solicita a Django que establezca la cookie CSRF."""

    return JsonResponse(
        {
            "detail": "CSRF cookie disponible.",
            "csrfToken": get_token(request),
        }
    )


@require_POST
@csrf_protect
@never_cache
def register_view(request):
    """Registra una cuenta y su empresa; la sesión se abre al confirmar el código del correo."""
    if request.user.is_authenticated:
        return JsonResponse(
            {"detail": "Cerrá la sesión actual antes de crear otra cuenta."}, status=403
        )
    if is_rate_limited(request, action="register", limit=REGISTRATION_LIMIT):
        return rate_limit_response()
    # El serializer valida el texto y conserva los errores por campo del formulario.
    data = parse_json_body(request, validate_text=False)
    if data is None:
        return JsonResponse({"detail": "Se esperaba un objeto JSON válido."}, status=400)
    try:
        user, _tenant = register_account(data=data, request=request)
    except ValidationError as exc:
        return JsonResponse(exc.detail, status=400)
    sent = send_new_code(request, user.pk, force=True)
    return verification_required(request, user, sent=sent, status=201)


def verification_required(request, user, *, sent, status):
    return JsonResponse(
        {
            "verification_required": True,
            "email": user.email,
            "email_sent": sent,
            "csrfToken": get_token(request),
        },
        status=status,
    )


def valid_email(value):
    return isinstance(value, str) and value.strip() and len(value.strip()) <= 254


def open_session(request, user):
    """Locks the account, honours MFA and opens the session after a valid credential."""
    with transaction.atomic():
        from . import mfa

        authenticated_hash = user.password
        user = mfa.lock_user(user.pk)
        if user is None or not constant_time_compare(user.password, authenticated_hash):
            return JsonResponse(
                {"detail": "Correo electrónico o contraseña incorrectos."}, status=401
            )
        device = mfa.lock_device(user)
        if device and device.confirmed_at:
            mfa.start_challenge(request, user, device)
            return JsonResponse(
                {"mfa_required": True, "expires_in": 300, "csrfToken": get_token(request)}
            )
        mfa.complete_login(request, user)
    return JsonResponse({"user": serialize_user(user), "csrfToken": get_token(request)})


@require_POST
@csrf_protect
@never_cache
def login_view(request):
    """Autentica al usuario y crea su sesión de Django."""

    data = parse_json_body(request)

    if data is None:
        return JsonResponse(
            {"detail": "Se esperaba un objeto JSON válido."},
            status=400,
        )

    email = data.get("email")
    password = data.get("password")

    if (
        not isinstance(email, str)
        or not email.strip()
        or len(email.strip()) > 254
        or not isinstance(password, str)
        or not password
        or len(password) > 4096
    ):
        return JsonResponse(
            {"detail": "Correo electrónico y contraseña son obligatorios."},
            status=400,
        )

    if is_rate_limited(request, action="login", limit=20) or is_rate_limited(
        request, action="login-account", limit=20, identity=email.strip().lower()
    ):
        return rate_limit_response()

    user = authenticate(
        request,
        email=email.strip().lower(),
        password=password,
    )

    if user is None:
        security_event(request, event="login", outcome="rejected")
        return JsonResponse(
            {"detail": "Correo electrónico o contraseña incorrectos."},
            status=401,
        )

    if not user.is_email_verified:
        # The password was right, so revealing the pending state leaks nothing new.
        sent = send_new_code(request, user.pk)
        return verification_required(request, user, sent=sent, status=403)
    return open_session(request, user)


@require_POST
@csrf_protect
@never_cache
def demo_login_view(request):
    """Abre una sesión de solo lectura en la empresa de demostración."""
    email = settings.DEMO_LOGIN_EMAIL
    if not email:
        return JsonResponse({"detail": "La demo no está disponible."}, status=404)
    if request.user.is_authenticated:
        return JsonResponse({"detail": "Cerrá la sesión actual antes de continuar."}, status=403)
    if is_rate_limited(request, action="demo-login", limit=30):
        return rate_limit_response()
    with transaction.atomic():
        from . import mfa

        user = mfa.lock_user(
            get_user_model()
            .objects.filter(email=email, is_active=True)
            .values_list("pk", flat=True)
            .first()
        )
        # Never hand out a session that can write: only a verified, viewer-only account.
        if (
            user is None
            or user.is_staff
            or user.is_superuser
            or user.has_usable_password()
            or not user.is_email_verified
            or not Membership.objects.filter(user=user, is_active=True).exists()
            or Membership.objects.filter(user=user).exclude(role=Membership.Role.VIEWER).exists()
        ):
            return JsonResponse({"detail": "La demo no está disponible."}, status=404)
        mfa.complete_login(request, user)
    return JsonResponse({"user": serialize_user(user), "csrfToken": get_token(request)})


@require_POST
@csrf_protect
@never_cache
def signup_code_confirm_view(request):
    """Confirma el código del correo y abre la sesión de esa cuenta."""
    if request.user.is_authenticated:
        return JsonResponse({"detail": "Cerrá la sesión actual antes de continuar."}, status=403)
    data = parse_json_body(request)
    if data is None:
        return JsonResponse({"detail": "Se esperaba un objeto JSON válido."}, status=400)
    email, code = data.get("email"), data.get("code")
    if (
        not valid_email(email)
        or not isinstance(code, str)
        or not code.isascii()
        or not (len(code) == 6 and code.isdigit())
    ):
        return JsonResponse({"detail": "Ingresá el código de 6 dígitos."}, status=400)
    email = email.strip().lower()
    if is_rate_limited(request, action="signup-code", limit=20) or is_rate_limited(
        request, action="signup-code-account", limit=10, identity=email
    ):
        return rate_limit_response()
    user = confirm_code(email, code)
    if user is None:
        security_event(request, event="signup_code", outcome="rejected")
        return JsonResponse(
            {"detail": "El código no es válido o venció. Pedí uno nuevo."}, status=400
        )
    security_event(request, event="signup_code", outcome="verified", actor=user)
    return open_session(request, user)


@require_POST
@csrf_protect
@never_cache
def signup_code_resend_view(request):
    """Reenvía el código sin revelar si el correo tiene una cuenta pendiente."""
    data = parse_json_body(request)
    if data is None or not valid_email(data.get("email")):
        return JsonResponse({"detail": "Ingresá un correo electrónico válido."}, status=400)
    email = data["email"].strip().lower()
    if is_rate_limited(request, action="signup-code-resend", limit=10) or is_rate_limited(
        request, action="signup-code-resend-account", limit=5, identity=email
    ):
        return rate_limit_response()
    user = get_user_model().objects.filter(email=email, is_active=True).only("pk").first()
    if user is not None:
        send_new_code(request, user.pk)
    return JsonResponse(
        {"detail": "Si hay una cuenta pendiente con ese correo, te enviamos un código nuevo."}
    )


@require_POST
@csrf_protect
@never_cache
def logout_view(request):
    """Cierra la sesión actual."""

    actor = request.user if request.user.is_authenticated else None
    try:
        if actor:
            security_event(request, event="logout", outcome="success", actor=actor)
    finally:
        logout(request)

    return JsonResponse(
        {
            "detail": "Sesión cerrada correctamente.",
        }
    )


@require_GET
@never_cache
def current_user_view(request):
    """Devuelve la identidad de la sesión actual."""

    if not request.user.is_authenticated:
        return JsonResponse(
            {"detail": "Autenticación requerida."},
            status=401,
        )

    if not request.user.is_active:
        logout(request)

        return JsonResponse(
            {"detail": "La cuenta está desactivada."},
            status=401,
        )

    return JsonResponse(
        {
            "user": serialize_user(request.user),
        }
    )


@extend_schema(responses=TenantListSerializer)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_tenants(request):
    memberships = (
        Membership.objects.filter(
            user=request.user,
            tenant__is_active=True,
            is_active=True,
        )
        .select_related("tenant")
        .order_by("tenant__name")
    )

    results = [
        {
            "id": str(membership.tenant_id),
            "name": membership.tenant.name,
            "slug": membership.tenant.slug,
            "role": membership.role,
        }
        for membership in memberships
    ]

    return Response({"results": results})
