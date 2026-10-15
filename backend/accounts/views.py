from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
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
    """Registra una cuenta, crea su empresa y abre una sesión normal."""
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
        user, tenant = register_account(data=data, request=request)
    except ValidationError as exc:
        return JsonResponse(exc.detail, status=400)
    login(request, user)
    return JsonResponse(
        {
            "user": serialize_user(user),
            "tenant": {
                "id": str(tenant.pk),
                "name": tenant.name,
                "slug": tenant.slug,
                "role": Membership.Role.OWNER,
            },
            "csrfToken": get_token(request),
        },
        status=201,
    )


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

    with transaction.atomic():
        security_event(request, event="login", outcome="success", actor=user)
        login(request, user)

    return JsonResponse(
        {
            "user": serialize_user(user),
            "csrfToken": get_token(request),
        }
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
