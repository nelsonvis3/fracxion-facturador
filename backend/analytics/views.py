from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from tenancy.permissions import TenantAccessPermission

from .services import AnalyticsFilters, overview, record_counts

ANALYST_ROLES = {"owner", "admin", "accountant"}


class OverviewView(APIView):
    permission_classes = [TenantAccessPermission]
    tenant_roles_by_action = {"get": ANALYST_ROLES}

    @extend_schema(parameters=[AnalyticsFilters], responses={200: dict})
    def get(self, request, tenant_id):
        return Response(overview(request.tenant, request.query_params))


class RecordCountsView(APIView):
    permission_classes = [TenantAccessPermission]

    @extend_schema(responses={200: dict})
    def get(self, request, tenant_id):
        return Response(record_counts(request.tenant))
