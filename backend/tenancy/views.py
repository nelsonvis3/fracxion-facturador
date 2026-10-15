from django.contrib.auth import get_user_model, login
from django.db import transaction
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.rate_limits import is_rate_limited
from accounts.security import security_event
from accounts.views import serialize_user

from .invitations import accept_invitation, create_invitation, manage_invitation, valid_invitation
from .mixins import TenantQuerySetMixin
from .models import BusinessSettings, Membership, TenantInvitation
from .permissions import TenantAccessPermission
from .serializers import (
    BusinessSettingsSerializer,
    InvitationAcceptSerializer,
    InvitationCreateSerializer,
    InvitationReadSerializer,
    InvitationTokenSerializer,
    MembershipReadSerializer,
    MembershipUpdateSerializer,
)
from .services import MANAGERS, change_member, settings_data, update_business_settings


class BusinessSettingsView(APIView):
    permission_classes = [TenantAccessPermission]

    @extend_schema(responses=BusinessSettingsSerializer)
    def get(self, request, tenant_id):
        return Response(BusinessSettingsSerializer(settings_data(request.tenant)).data)

    @extend_schema(request=BusinessSettingsSerializer, responses=BusinessSettingsSerializer)
    def patch(self, request, tenant_id):
        serializer = BusinessSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        result = update_business_settings(
            tenant_id=tenant_id, actor=request.user, data=serializer.validated_data, request=request
        )
        return Response(BusinessSettingsSerializer(result).data)


class CompanyLogoView(APIView):
    permission_classes = [TenantAccessPermission]

    @extend_schema(responses={(200, "image/png"): bytes})
    def get(self, request, tenant_id):
        settings = BusinessSettings.objects.filter(tenant=request.tenant).only("logo").first()
        if settings is None or not settings.logo:
            raise NotFound("La empresa no tiene un logo disponible.")
        response = HttpResponse(bytes(settings.logo), content_type="image/png")
        response["Content-Disposition"] = 'inline; filename="company-logo.png"'
        response["X-Content-Type-Options"] = "nosniff"
        return response


class MembershipViewSet(
    TenantQuerySetMixin, mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    queryset = Membership.objects.select_related("user").order_by("user__email")
    permission_classes = [TenantAccessPermission]
    tenant_roles_by_action = {"list": MANAGERS, "partial_update": MANAGERS}
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        return (
            MembershipUpdateSerializer
            if self.action == "partial_update"
            else MembershipReadSerializer
        )

    @extend_schema(request=MembershipUpdateSerializer, responses=MembershipReadSerializer)
    def partial_update(self, request, *args, **kwargs):
        member = self.get_object()
        serializer = MembershipUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = change_member(
            tenant_id=request.tenant.pk,
            member_id=member.pk,
            actor=request.user,
            request=request,
            **serializer.validated_data,
        )
        return Response(MembershipReadSerializer(member).data)


class InvitationViewSet(
    TenantQuerySetMixin, mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    queryset = TenantInvitation.objects.all()
    permission_classes = [TenantAccessPermission]
    tenant_roles_by_action = {
        "list": MANAGERS,
        "create": MANAGERS,
        "resend": MANAGERS,
        "revoke": MANAGERS,
    }
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        return InvitationCreateSerializer if self.action == "create" else InvitationReadSerializer

    def throttle_delivery(self, request):
        if is_rate_limited(
            request,
            action="invitations",
            limit=10,
            identity=f"{request.tenant.pk}:{request.user.pk}",
        ):
            raise Throttled(
                wait=900,
                detail="Alcanzaste el límite de invitaciones. Volvé a intentarlo más tarde.",
            )

    @extend_schema(request=InvitationCreateSerializer, responses={201: InvitationReadSerializer})
    def create(self, request, *args, **kwargs):
        self.throttle_delivery(request)
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = create_invitation(
            tenant_id=request.tenant.pk,
            actor=request.user,
            request=request,
            **serializer.validated_data,
        )
        return Response(InvitationReadSerializer(invitation).data, status=201)

    @extend_schema(request=None, responses=InvitationReadSerializer)
    @action(detail=True, methods=["post"])
    def resend(self, request, *args, **kwargs):
        self.throttle_delivery(request)
        invitation = manage_invitation(
            tenant_id=request.tenant.pk,
            actor=request.user,
            invitation_id=self.get_object().pk,
            resend=True,
            request=request,
        )
        return Response(InvitationReadSerializer(invitation).data)

    @extend_schema(request=None, responses=InvitationReadSerializer)
    @action(detail=True, methods=["post"])
    def revoke(self, request, *args, **kwargs):
        invitation = manage_invitation(
            tenant_id=request.tenant.pk,
            actor=request.user,
            invitation_id=self.get_object().pk,
            request=request,
        )
        return Response(InvitationReadSerializer(invitation).data)


@method_decorator(csrf_protect, name="dispatch")
class InvitationPreviewView(APIView):
    permission_classes = [AllowAny]
    serializer_class = InvitationTokenSerializer

    def parse_token(self, request, serializer_class):
        if is_rate_limited(request, action="invitation-accept", limit=20):
            raise Throttled(wait=900)
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @extend_schema(request=InvitationTokenSerializer, responses={200: dict})
    def post(self, request):
        data = self.parse_token(request, InvitationTokenSerializer)
        invitation = valid_invitation(data["token"])
        return Response(
            {
                "company_name": invitation.tenant.name,
                "email": invitation.email,
                "role": invitation.role,
                "expires_at": invitation.expires_at,
                "account_exists": get_user_model().objects.filter(email=invitation.email).exists(),
            }
        )


class InvitationAcceptView(InvitationPreviewView):
    @extend_schema(request=InvitationAcceptSerializer, responses={200: dict})
    def post(self, request):
        data = self.parse_token(request, InvitationAcceptSerializer)
        with transaction.atomic():
            user, member = accept_invitation(actor=request.user, request=request, **data)
            login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
            security_event(request, event="login", outcome="invitation_accepted", actor=user)
        return Response(
            {
                "user": serialize_user(user),
                "tenant": {
                    "id": str(member.tenant_id),
                    "name": member.tenant.name,
                    "slug": member.tenant.slug,
                    "role": member.role,
                },
            }
        )
