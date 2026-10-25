"""Explicit user-requested verification; no automatic lockout or email on registration."""

import logging
import uuid
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound, Throttled, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from tenancy.serializers import StrictInputMixin

from .rate_limits import is_rate_limited
from .security import security_event

logger = logging.getLogger(__name__)
SALT = "accounts.email-verification.v1"
MAX_AGE = 24 * 60 * 60
INVALID = "El enlace no es válido o venció. Solicitá uno nuevo desde tu cuenta."


def verification_token(user):
    return signing.dumps(
        {"user": str(user.pk), "email": user.email, "nonce": str(user.email_verification_nonce)},
        salt=SALT,
    )


class EmptyInput(StrictInputMixin, serializers.Serializer):
    pass


class VerificationInput(StrictInputMixin, serializers.Serializer):
    token = serializers.CharField(max_length=2048, write_only=True)


class VerificationStatus(serializers.Serializer):
    email = serializers.EmailField()
    verified = serializers.BooleanField()
    verified_at = serializers.DateTimeField(allow_null=True)


class VerificationResult(serializers.Serializer):
    detail = serializers.CharField()


class EmailDeliveryUnavailable(APIException):
    status_code = 503
    default_detail = "No se pudo entregar el correo. Intentá nuevamente más tarde."
    default_code = "email_delivery_unavailable"


class VerificationStatusView(APIView):
    @extend_schema(responses=VerificationStatus)
    def get(self, request):
        user = get_user_model().objects.filter(pk=request.user.pk, is_active=True).first()
        if user is None:
            raise NotFound()
        return Response(
            {
                "email": user.email,
                "verified": user.is_email_verified,
                "verified_at": user.email_verified_at if user.is_email_verified else None,
            }
        )


class VerificationRequestView(APIView):
    @extend_schema(request=EmptyInput, responses=VerificationResult)
    def post(self, request):
        serializer = EmptyInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        if is_rate_limited(
            request, action="verify-email-user", limit=5, identity=str(request.user.pk)
        ) or is_rate_limited(request, action="verify-email-ip", limit=20):
            raise Throttled(wait=900)
        with transaction.atomic():
            user = (
                get_user_model()
                .objects.select_for_update(no_key=True)
                .filter(pk=request.user.pk, is_active=True)
                .first()
            )
            if user is None:
                raise NotFound()
            if user.is_email_verified:
                return Response({"detail": "Tu correo ya está verificado."})
            user.email_verification_nonce = uuid.uuid4()
            user.save(update_fields=["email_verification_nonce"])
            token = verification_token(user)
            security_event(
                request, event="email_verification_request", outcome="requested", actor=user
            )
        # SMTP is deliberately outside the database transaction. Only the latest
        # nonce works; manual resend can recover a failed transport. This is not
        # described as a durable outbox or proof of inbox delivery.
        frontend = urlsplit(settings.FRONTEND_PASSWORD_RESET_URL)
        link = urlunsplit((frontend.scheme, frontend.netloc, "/verify-email", "", "token=" + token))
        try:
            sent = send_mail(
                "Verificá tu correo en Fracxion",
                f"Confirmá tu correo abriendo este enlace:\n\n{link}\n\nVence en 24 horas y puede usarse una sola vez. Solo el último correo solicitado es válido. Si no lo solicitaste, ignoralo.",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            if sent != 1:
                raise RuntimeError("email_not_accepted")
        except Exception:
            security_event(
                request, event="email_verification_delivery", outcome="failed", actor=user
            )
            logger.exception(
                "email_verification_delivery_failed",
                extra={"request_id": getattr(request, "request_id", "")},
            )
            raise EmailDeliveryUnavailable() from None
        security_event(
            request,
            event="email_verification_delivery",
            outcome="accepted_by_transport",
            actor=user,
        )
        return Response(
            {
                "detail": "El servicio de correo aceptó el mensaje. Revisá tu bandeja y spam; el enlace vence en 24 horas. Solo el último enlace solicitado es válido."
            }
        )


@method_decorator(csrf_protect, name="dispatch")
class VerificationConfirmView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=VerificationInput, responses=VerificationResult)
    def post(self, request):
        if is_rate_limited(request, action="verify-email-confirm", limit=20):
            raise Throttled(wait=900)
        serializer = VerificationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = signing.loads(serializer.validated_data["token"], salt=SALT, max_age=MAX_AGE)
            if not isinstance(payload, dict):
                raise ValueError()
            user_id = int(payload.get("user", ""))
            if not 0 < user_id <= 9223372036854775807:
                raise ValueError()
        except (signing.BadSignature, ValueError, TypeError, AttributeError):
            raise ValidationError(INVALID) from None
        with transaction.atomic():
            user = (
                get_user_model()
                .objects.select_for_update(no_key=True)
                .filter(pk=user_id, is_active=True)
                .first()
            )
            if (
                user is None
                or user.is_email_verified
                or payload.get("email") != user.email
                or payload.get("nonce") != str(user.email_verification_nonce)
            ):
                raise ValidationError(INVALID)
            # A logged-in person must not unknowingly verify another account.
            if request.user.is_authenticated and request.user.pk != user.pk:
                raise ValidationError(
                    "El enlace corresponde a otra cuenta. Cerrá esta sesión antes de continuar."
                )
            user.verified_email = user.email
            user.email_verified_at = timezone.now()
            user.email_verification_nonce = uuid.uuid4()
            user.save(
                update_fields=["verified_email", "email_verified_at", "email_verification_nonce"]
            )
            security_event(request, event="email_verification", outcome="verified", actor=user)
        return Response({"detail": "Correo verificado. Ya podés continuar en tu cuenta."})
