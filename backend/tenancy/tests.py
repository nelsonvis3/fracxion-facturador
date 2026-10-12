from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from .mixins import TenantQuerySetMixin
from .models import Membership, Tenant
from .permissions import TenantAccessPermission

User = get_user_model()


class MembershipQueryViewBase:
    """Vista mínima para probar el filtrado del queryset."""

    def get_queryset(self):
        return Membership.objects.all()


class MembershipQueryView(
    TenantQuerySetMixin,
    MembershipQueryViewBase,
):
    pass


class TenantSecurityTests(TestCase):
    """Pruebas de aislamiento, membresías y roles."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            name="Empresa Alpha",
            slug="empresa-alpha",
        )

        self.tenant_b = Tenant.objects.create(
            name="Empresa Beta",
            slug="empresa-beta",
        )

        self.user_a = User.objects.create_user(
            email="usuario.alpha@example.com",
            password="TestPassword123!",
        )

        self.user_b = User.objects.create_user(
            email="usuario.beta@example.com",
            password="TestPassword123!",
        )

        self.membership_a = Membership.objects.create(
            tenant=self.tenant_a,
            user=self.user_a,
            role=Membership.Role.OWNER,
        )

        self.membership_b = Membership.objects.create(
            tenant=self.tenant_b,
            user=self.user_b,
            role=Membership.Role.OWNER,
        )

        self.permission = TenantAccessPermission()

    def make_request(self, user, method="GET", tenant_id=None):
        request = SimpleNamespace(
            user=user,
            method=method,
        )

        kwargs = {}

        if tenant_id is not None:
            kwargs["tenant_id"] = str(tenant_id)

        view = SimpleNamespace(kwargs=kwargs)

        return request, view

    def test_member_can_access_own_tenant(self):
        request, view = self.make_request(
            self.user_a,
            tenant_id=self.tenant_a.pk,
        )

        allowed = self.permission.has_permission(
            request,
            view,
        )

        self.assertTrue(allowed)
        self.assertEqual(request.tenant, self.tenant_a)
        self.assertEqual(
            request.membership,
            self.membership_a,
        )

    def test_member_cannot_access_another_tenant(self):
        request, view = self.make_request(
            self.user_a,
            tenant_id=self.tenant_b.pk,
        )

        allowed = self.permission.has_permission(
            request,
            view,
        )

        self.assertFalse(allowed)

    def test_anonymous_user_is_denied(self):
        request, view = self.make_request(
            AnonymousUser(),
            tenant_id=self.tenant_a.pk,
        )

        allowed = self.permission.has_permission(
            request,
            view,
        )

        self.assertFalse(allowed)

    def test_inactive_user_is_denied(self):
        self.user_a.is_active = False
        self.user_a.save(update_fields=["is_active"])

        request, view = self.make_request(
            self.user_a,
            tenant_id=self.tenant_a.pk,
        )

        allowed = self.permission.has_permission(
            request,
            view,
        )

        self.assertFalse(allowed)

    def test_inactive_membership_is_denied(self):
        self.membership_a.is_active = False
        self.membership_a.save()

        request, view = self.make_request(
            self.user_a,
            tenant_id=self.tenant_a.pk,
        )

        allowed = self.permission.has_permission(
            request,
            view,
        )

        self.assertFalse(allowed)

    def test_inactive_tenant_is_denied(self):
        self.tenant_a.is_active = False
        self.tenant_a.save()

        request, view = self.make_request(
            self.user_a,
            tenant_id=self.tenant_a.pk,
        )

        allowed = self.permission.has_permission(
            request,
            view,
        )

        self.assertFalse(allowed)

    def test_missing_tenant_id_is_denied(self):
        request, view = self.make_request(self.user_a)

        allowed = self.permission.has_permission(
            request,
            view,
        )

        self.assertFalse(allowed)

    def test_viewer_can_read_but_cannot_write(self):
        viewer = User.objects.create_user(
            email="visor@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            tenant=self.tenant_a,
            user=viewer,
            role=Membership.Role.VIEWER,
        )

        read_request, read_view = self.make_request(
            viewer,
            method="GET",
            tenant_id=self.tenant_a.pk,
        )

        write_request, write_view = self.make_request(
            viewer,
            method="POST",
            tenant_id=self.tenant_a.pk,
        )

        self.assertTrue(
            self.permission.has_permission(
                read_request,
                read_view,
            )
        )

        self.assertFalse(
            self.permission.has_permission(
                write_request,
                write_view,
            )
        )

    def test_owner_can_write_to_own_tenant(self):
        request, view = self.make_request(
            self.user_a,
            method="POST",
            tenant_id=self.tenant_a.pk,
        )

        allowed = self.permission.has_permission(
            request,
            view,
        )

        self.assertTrue(allowed)

    def test_queryset_only_contains_authorized_tenant(self):
        request, _ = self.make_request(
            self.user_a,
            tenant_id=self.tenant_a.pk,
        )

        view = MembershipQueryView()
        view.request = request
        view.kwargs = {
            "tenant_id": str(self.tenant_a.pk),
        }

        allowed = self.permission.has_permission(
            request,
            view,
        )

        self.assertTrue(allowed)

        memberships = view.get_queryset()

        self.assertEqual(
            list(memberships),
            [self.membership_a],
        )

        self.assertFalse(
            memberships.filter(
                tenant=self.tenant_b,
            ).exists()
        )
