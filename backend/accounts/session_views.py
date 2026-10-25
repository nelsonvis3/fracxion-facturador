from django.contrib.auth import get_user_model, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError as PasswordError
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from tenancy.serializers import StrictInputMixin

from .models import AccountSession
from .rate_limits import is_rate_limited
from .security import security_event


class AccountSessionSerializer(serializers.ModelSerializer):
    expires_at = serializers.DateTimeField(source="session.expire_date", read_only=True)
    current = serializers.SerializerMethodField()

    @extend_schema_field(bool)
    def get_current(self, obj):
        return obj.session_id == self.context["request"].session.session_key

    class Meta:
        model = AccountSession
        fields = ["id", "device", "ip_address", "first_seen", "last_seen", "expires_at", "current"]


class CurrentPassword(StrictInputMixin, serializers.Serializer):
    current_password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


class ChangePassword(CurrentPassword):
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    password_confirm = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


def throttle_sensitive(request):
    if is_rate_limited(
        request, action="account-sensitive", limit=10, identity=str(request.user.pk)
    ) or is_rate_limited(request, action="account-sensitive-ip", limit=20):
        raise Throttled(wait=900)


def locked_account(request, data):
    user = (
        get_user_model()
        .objects.select_for_update(no_key=True)
        .filter(pk=request.user.pk, is_active=True)
        .first()
    )
    if user is None:
        raise NotFound()
    if not user.check_password(data["current_password"]):
        raise ValidationError({"current_password": "La contraseña actual no es correcta."})
    return user


class AccountSessionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = AccountSession.objects.none()
    serializer_class = AccountSessionSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return AccountSession.objects.filter(
            user=self.request.user, session__expire_date__gt=timezone.now()
        ).select_related("session")

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def revoke(self, request, pk=None):
        if is_rate_limited(
            request, action="revoke-session", limit=30, identity=str(request.user.pk)
        ):
            raise Throttled(wait=900)
        item = self.get_object()
        current = item.session_id == request.session.session_key
        security_event(request, event="session_revoked", outcome="success", actor=request.user)
        Session.objects.filter(
            session_key=item.session_id, account_record__user=request.user
        ).delete()
        if current:
            logout(request)
        return Response({"detail": "Sesión cerrada.", "current": current})

    @extend_schema(request=CurrentPassword, responses={200: dict})
    @action(detail=False, methods=["post"], url_path="revoke-others")
    def revoke_others(self, request):
        throttle_sensitive(request)
        serializer = CurrentPassword(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = locked_account(request, serializer.validated_data)
            user.session_version += 1
            user.save(update_fields=["session_version"])
            # Django rotates the current key and preserves this authenticated device.
            update_session_auth_hash(request, user)
            Session.objects.filter(account_record__user=user).exclude(
                session_key=request.session.session_key
            ).delete()
            security_event(request, event="other_sessions_revoked", outcome="success", actor=user)
        return Response(
            {"detail": "Las otras sesiones quedaron invalidadas. Esta sesión continúa activa."}
        )


class ChangePasswordView(APIView):
    @extend_schema(request=ChangePassword, responses={200: dict})
    def post(self, request):
        throttle_sensitive(request)
        serializer = ChangePassword(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["password"] != data["password_confirm"]:
            raise ValidationError({"password_confirm": "Las contraseñas no coinciden."})
        with transaction.atomic():
            user = locked_account(request, data)
            try:
                validate_password(data["password"], user=user)
            except PasswordError as exc:
                raise ValidationError({"password": exc.messages}) from exc
            if user.check_password(data["password"]):
                raise ValidationError({"password": "Elegí una contraseña diferente de la actual."})
            user.set_password(data["password"])
            user.save(update_fields=["password"])
            update_session_auth_hash(request, user)
            Session.objects.filter(account_record__user=user).exclude(
                session_key=request.session.session_key
            ).delete()
            security_event(request, event="password_changed", outcome="success", actor=user)
        return Response(
            {"detail": "Contraseña actualizada. Las otras sesiones quedaron invalidadas."}
        )
