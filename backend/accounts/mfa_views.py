from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from config.parsers import parse_json_body

from . import mfa
from .models import AccountMFA
from .rate_limits import is_rate_limited, rate_limit_response
from .security import security_event
from .session_views import CurrentPassword, locked_account, throttle_sensitive
from .views import serialize_user


class MFACredential(CurrentPassword):
    code = serializers.CharField(max_length=64, trim_whitespace=True, write_only=True)


class MFAAction(MFACredential):
    action = serializers.ChoiceField(choices=["confirm", "disable", "recovery"])


class MFAStatusView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request):
        device = AccountMFA.objects.filter(user=request.user, confirmed_at__isnull=False).first()
        return Response(
            {
                "available": bool(settings.MFA_ENCRYPTION_KEYS),
                "enabled": bool(device),
                "recovery_codes_remaining": len(device.recovery_hashes) if device else 0,
            }
        )

    @extend_schema(request=CurrentPassword, responses={200: dict})
    def post(self, request):
        throttle_sensitive(request)
        data = CurrentPassword(data=request.data)
        data.is_valid(raise_exception=True)
        if not settings.MFA_ENCRYPTION_KEYS:
            return Response(
                {"detail": "El administrador debe configurar el cifrado MFA."}, status=503
            )
        with transaction.atomic():
            user = locked_account(request, data.validated_data)
            device = mfa.lock_device(user)
            if device and device.confirmed_at:
                raise ValidationError({"detail": "MFA ya está activado."})
            _, secret, uri = mfa.setup(user)
            security_event(request, event="mfa_setup", outcome="success", actor=user)
        return Response({"secret": secret, "uri": uri, "expires_in": 600})


class MFAManageView(APIView):
    @extend_schema(request=MFAAction, responses={200: dict})
    def post(self, request):
        throttle_sensitive(request)
        data = MFAAction(data=request.data)
        data.is_valid(raise_exception=True)
        data = data.validated_data
        with transaction.atomic():
            user = locked_account(request, data)
            device = mfa.lock_device(user)
            confirming = data["action"] == "confirm"
            if (
                not device
                or (
                    confirming
                    and (device.confirmed_at or device.setup_expires_at <= timezone.now())
                )
                or (not confirming and not device.confirmed_at)
            ):
                raise ValidationError({"detail": "Configuración no disponible o vencida."})
            if not mfa.verify(device, data["code"], recovery=not confirming):
                raise ValidationError({"code": "Código inválido o ya utilizado."})
            result = {}
            if data["action"] == "disable":
                device.delete()
                device = None
                detail = "MFA desactivado. Se cerraron las otras sesiones."
            else:
                if confirming:
                    device.confirmed_at = timezone.now()
                    device.save(update_fields=["confirmed_at"])
                result["recovery_codes"] = mfa.recovery_codes(device)
                detail = "MFA activado." if confirming else "Códigos de recuperación renovados."
            mfa.refresh_sessions(request, user, device)
            security_event(request, event=f"mfa_{data['action']}", outcome="success", actor=user)
        return Response({"detail": detail, **result})


@require_POST
@csrf_protect
@never_cache
def mfa_login_view(request):
    challenge = request.session.get(mfa.CHALLENGE) or {}
    identity = str(challenge.get("user", "anonymous"))
    if is_rate_limited(request, action="mfa-login-ip", limit=20) or is_rate_limited(
        request, action="mfa-login-account", limit=10, identity=identity
    ):
        return rate_limit_response()
    data = parse_json_body(request)
    if (
        not data
        or set(data) != {"code"}
        or not isinstance(data["code"], str)
        or len(data["code"]) > 64
    ):
        return JsonResponse({"detail": "Ingresá un código válido."}, status=400)
    user = mfa.challenge_user(request, data["code"].strip())
    if user is None:
        security_event(request, event="mfa_login", outcome="rejected")
        return JsonResponse(
            {"detail": "Código inválido, utilizado o solicitud vencida."}, status=401
        )
    return JsonResponse({"user": serialize_user(user), "csrfToken": get_token(request)})
