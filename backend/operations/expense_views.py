from django.db import transaction
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from accounts.rate_limits import is_rate_limited
from auditlog.models import AuditEvent
from auditlog.services import record_audit_event
from tenancy.mixins import TenantQuerySetMixin
from tenancy.permissions import TenantAccessPermission
from tenancy.services import lock_company

from .expense_serializers import (
    CategorySerializer,
    ExpenseInput,
    ExpensePaymentInput,
    ExpensePaymentSerializer,
    ExpenseReadSerializer,
)
from .expenses import (
    FINANCE_ROLES,
    expense_query,
    pay_expense,
    post_expense,
    reverse_expense_payment,
    save_category,
    save_expense,
    void_expense,
)
from .filters import ExpenseFilter
from .models import Expense, ExpenseCategory, ExpensePayment
from .serializers import ReversalInput


class CategoryViewSet(TenantQuerySetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [TenantAccessPermission]
    queryset = ExpenseCategory.objects.all()
    serializer_class = CategorySerializer
    tenant_roles_by_action = {key: FINANCE_ROLES for key in ["list", "create", "partial_update"]}
    http_method_names = ["get", "post", "patch", "head", "options"]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["is_active"]
    search_fields = ["name"]

    def create(self, request, *args, **kwargs):
        category = save_category(
            tenant_id=request.tenant.pk, actor=request.user, data=request.data, request=request
        )
        return Response(self.get_serializer(category).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        category = save_category(
            tenant_id=request.tenant.pk,
            actor=request.user,
            data=request.data,
            category_id=self.get_object().pk,
            request=request,
        )
        return Response(self.get_serializer(category).data)


class ExpenseViewSet(
    TenantQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [TenantAccessPermission]
    queryset = Expense.objects.none()
    serializer_class = ExpenseReadSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    tenant_roles_by_action = {
        key: FINANCE_ROLES
        for key in [
            "list",
            "retrieve",
            "create",
            "partial_update",
            "register",
            "void",
            "payments",
            "attachment",
        ]
    }
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = ExpenseFilter
    search_fields = ["description", "reference", "supplier_name_snapshot"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        query = expense_query(self.request.tenant)
        for param, field in [
            ("date_from", "incurred_on__gte"),
            ("date_to", "incurred_on__lte"),
            ("due_from", "due_date__gte"),
            ("due_to", "due_date__lte"),
        ]:
            if self.request.query_params.get(param):
                value = serializers.DateField().run_validation(self.request.query_params[param])
                query = query.filter(**{field: value})
        payment = self.request.query_params.get("payment_status")
        if payment not in {None, "", "unpaid", "paid"}:
            raise serializers.ValidationError({"payment_status": "Estado de pago inválido."})
        if payment:
            query = (
                query.filter(status="posted", balance__gt=0)
                if payment == "unpaid"
                else query.filter(status="posted", balance=0)
            )
        return query

    def output(self, expense, status=200):
        return Response(
            self.get_serializer(expense_query(self.request.tenant).get(pk=expense.pk)).data,
            status=status,
        )

    @extend_schema(request=ExpenseInput, responses={201: ExpenseReadSerializer})
    def create(self, request, *args, **kwargs):
        return self.output(
            save_expense(
                tenant_id=request.tenant.pk, actor=request.user, data=request.data, request=request
            ),
            201,
        )

    @extend_schema(request=ExpenseInput, responses=ExpenseReadSerializer)
    def partial_update(self, request, *args, **kwargs):
        return self.output(
            save_expense(
                tenant_id=request.tenant.pk,
                actor=request.user,
                data=request.data,
                expense_id=self.get_object().pk,
                request=request,
            )
        )

    @extend_schema(request=None, responses=ExpenseReadSerializer)
    @action(detail=True, methods=["post"], url_path="post")
    def register(self, request, *args, **kwargs):
        return self.output(
            post_expense(
                tenant_id=request.tenant.pk,
                actor=request.user,
                expense_id=self.get_object().pk,
                request=request,
            )
        )

    @extend_schema(request=ReversalInput, responses=ExpenseReadSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, *args, **kwargs):
        return self.output(
            void_expense(
                tenant_id=request.tenant.pk,
                actor=request.user,
                expense_id=self.get_object().pk,
                data=request.data,
                request=request,
            )
        )

    @extend_schema(methods=["GET"], responses=ExpensePaymentSerializer(many=True))
    @extend_schema(
        methods=["POST"],
        request=ExpensePaymentInput,
        responses={201: ExpensePaymentSerializer},
        parameters=[
            OpenApiParameter(name="Idempotency-Key", location=OpenApiParameter.HEADER, type=str)
        ],
    )
    @action(detail=True, methods=["get", "post"])
    def payments(self, request, *args, **kwargs):
        expense = self.get_object()
        if request.method == "POST":
            payment = pay_expense(
                tenant_id=request.tenant.pk,
                actor=request.user,
                expense_id=expense.pk,
                data=request.data,
                idempotency_key=request.headers.get("Idempotency-Key"),
                request=request,
            )
            return Response(
                ExpensePaymentSerializer(
                    ExpensePayment.objects.select_related("reversal").get(pk=payment.pk)
                ).data,
                status=201,
            )
        query = ExpensePayment.objects.filter(
            tenant=request.tenant, expense=expense
        ).select_related("reversal")
        page = self.paginate_queryset(query)
        return self.get_paginated_response(ExpensePaymentSerializer(page, many=True).data)

    @extend_schema(responses={(200, "image/png"): bytes})
    @action(detail=True, methods=["get"])
    @transaction.atomic
    def attachment(self, request, *args, **kwargs):
        lock_company(request.tenant.pk, actor=request.user, roles=FINANCE_ROLES)
        expense = self.get_object()
        from rest_framework.exceptions import Throttled

        if is_rate_limited(
            request,
            action="expense_attachment",
            limit=60,
            identity=f"{request.tenant.pk}:{request.user.pk}",
        ):
            raise Throttled(wait=900)
        if expense.attachment is None:
            raise NotFound()
        record_audit_event(
            tenant=request.tenant,
            actor=request.user,
            request=request,
            action=AuditEvent.Action.EXPORT,
            entity_type="operations.expense_attachment",
            entity_id=expense.pk,
        )
        response = HttpResponse(bytes(expense.attachment), content_type="image/png")
        response["Content-Disposition"] = f'attachment; filename="gasto-{expense.pk}.png"'
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ExpensePaymentViewSet(TenantQuerySetMixin, viewsets.GenericViewSet):
    queryset = ExpensePayment.objects.all()
    serializer_class = ExpensePaymentSerializer
    permission_classes = [TenantAccessPermission]
    tenant_roles_by_action = {"reverse": FINANCE_ROLES}
    http_method_names = ["post", "options"]

    @extend_schema(request=ReversalInput, responses=ExpensePaymentSerializer)
    @action(detail=True, methods=["post"])
    def reverse(self, request, *args, **kwargs):
        payment = self.get_object()
        reverse_expense_payment(
            tenant_id=request.tenant.pk,
            actor=request.user,
            payment_id=payment.pk,
            data=request.data,
            request=request,
        )
        return Response(
            ExpensePaymentSerializer(
                ExpensePayment.objects.select_related("reversal").get(pk=payment.pk)
            ).data
        )
