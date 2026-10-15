from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import PermissionDenied, ValidationError

from auditlog.models import AuditEvent

from .models import Membership, Tenant
from .services import change_member, guard_user_deactivation

User = get_user_model()


class TeamFoundationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Foundation", slug="foundation")
        self.owner = User.objects.create_user(email="owner@foundation.example")
        self.member = Membership.objects.create(tenant=self.tenant, user=self.owner, role="owner")
        self.platform = User.objects.create_superuser(
            email="platform@foundation.example", password="SyntheticPlatformPassword2026!"
        )

    def change(self, **kwargs):
        return change_member(
            tenant_id=self.tenant.pk, member_id=self.member.pk, actor=self.owner, **kwargs
        )

    def test_last_owner_cannot_be_demoted_or_deactivated(self):
        for data in [{"role": "viewer"}, {"is_active": False}]:
            with self.assertRaises(ValidationError):
                self.change(**data)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)
        self.assertEqual(self.member.role, "owner")

    def test_platform_admin_also_obeys_last_owner(self):
        with self.assertRaises(ValidationError):
            change_member(
                tenant_id=self.tenant.pk,
                member_id=self.member.pk,
                actor=self.platform,
                platform=True,
                is_active=False,
            )

    def test_owner_change_audited_and_audit_failure_rolls_back(self):
        other = User.objects.create_user(email="second@foundation.example")
        Membership.objects.create(tenant=self.tenant, user=other, role="owner")
        with patch(
            "tenancy.services.record_audit_event", side_effect=RuntimeError("audit unavailable")
        ):
            with self.assertRaises(RuntimeError):
                self.change(role="viewer")
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, "owner")
        self.change(role="viewer")
        event = AuditEvent.objects.get(entity_type="tenancy.membership")
        self.assertEqual(event.tenant, self.tenant)
        self.assertEqual(event.actor, self.owner)
        self.assertEqual(event.changes["fields"]["role"], {"before": "owner", "after": "viewer"})

    def test_admin_cannot_modify_owner_or_promote_self(self):
        admin = User.objects.create_user(email="admin@foundation.example")
        membership = Membership.objects.create(tenant=self.tenant, user=admin, role="admin")
        for target in [membership, self.member]:
            with self.assertRaises(PermissionDenied):
                change_member(
                    tenant_id=self.tenant.pk, member_id=target.pk, actor=admin, role="owner"
                )

    def test_admin_form_reports_error_without_500(self):
        self.client.force_login(self.platform)
        response = self.client.post(
            f"/admin/tenancy/membership/{self.member.pk}/change/",
            {"role": "viewer", "_save": "Save"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "al menos un propietario")
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)

    def test_admin_change_generates_business_audit(self):
        user = User.objects.create_user(email="viewer@foundation.example")
        member = Membership.objects.create(tenant=self.tenant, user=user, role="viewer")
        self.client.force_login(self.platform)
        response = self.client.post(
            f"/admin/tenancy/membership/{member.pk}/change/",
            {"role": "sales", "is_active": "on", "_save": "Save"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant, entity_id=str(member.pk), actor=self.platform
            ).exists()
        )

    def test_deactivating_last_owner_user_is_rejected(self):
        from django.core.exceptions import ValidationError as ModelValidationError

        with self.assertRaises(ModelValidationError):
            guard_user_deactivation(self.owner.pk)

    def test_foreign_platform_flag_never_authorizes_normal_owner(self):
        with self.assertRaises(PermissionDenied):
            self.change(platform=True, role="viewer")


class ConcurrentOwnerTests(TransactionTestCase):
    def test_invitation_acceptance_deactivation_and_demotion_cannot_orphan_company(self):
        from datetime import timedelta

        from django.core.exceptions import ValidationError as ModelValidationError
        from django.utils import timezone

        from .invitations import accept_invitation, token_digest
        from .models import TenantInvitation

        tenant = Tenant.objects.create(name="Three way race", slug="three-way-race")
        owner = User.objects.create_user(email="first@threeway.example")
        target = User.objects.create_user(email="target@threeway.example")
        platform = User.objects.create_superuser(
            email="platform@threeway.example", password="SyntheticPlatformPassword2026!"
        )
        original = Membership.objects.create(tenant=tenant, user=owner, role="owner")
        token = "t" * 43
        TenantInvitation.objects.create(
            tenant=tenant,
            email=target.email,
            role="owner",
            invited_by=owner,
            token_digest=token_digest(token),
            expires_at=timezone.now() + timedelta(days=7),
        )
        barrier = Barrier(3)

        def operate(which):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                if which == "accept":
                    accept_invitation(token=token, actor=target)
                elif which == "demote":
                    change_member(
                        tenant_id=tenant.pk,
                        member_id=original.pk,
                        actor=platform,
                        platform=True,
                        role="viewer",
                    )
                else:
                    with transaction.atomic():
                        guard_user_deactivation(target.pk)
                        User.objects.filter(pk=target.pk).update(is_active=False)
                return "changed"
            except (ValidationError, PermissionDenied, ModelValidationError):
                return "protected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(operate, ["accept", "demote", "deactivate"]))
        self.assertGreaterEqual(
            Membership.objects.filter(
                tenant=tenant, role="owner", is_active=True, user__is_active=True
            ).count(),
            1,
        )

    def test_two_demotions_cannot_remove_both_owners(self):
        tenant = Tenant.objects.create(name="Concurrent owners", slug="concurrent-owners")
        platform = User.objects.create_superuser(
            email="platform@race.example", password="SyntheticPlatformPassword2026!"
        )
        members = [
            Membership.objects.create(
                tenant=tenant,
                user=User.objects.create_user(email=f"owner{n}@race.example"),
                role="owner",
            )
            for n in range(2)
        ]
        barrier = Barrier(2)

        def demote(member):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                change_member(
                    tenant_id=tenant.pk,
                    member_id=member.pk,
                    actor=platform,
                    platform=True,
                    role="viewer",
                )
                return "changed"
            except ValidationError:
                return "protected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(demote, members))
        self.assertCountEqual(outcomes, ["changed", "protected"])
        self.assertEqual(
            Membership.objects.filter(
                tenant=tenant, role="owner", is_active=True, user__is_active=True
            ).count(),
            1,
        )

    def test_two_user_deactivations_are_serialized(self):
        from django.core.exceptions import ValidationError as ModelValidationError

        tenant = Tenant.objects.create(name="Concurrent users", slug="concurrent-users")
        users = [User.objects.create_user(email=f"user{n}@race.example") for n in range(2)]
        for user in users:
            Membership.objects.create(tenant=tenant, user=user, role="owner")
        barrier = Barrier(2)

        def deactivate(user):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                with transaction.atomic():
                    guard_user_deactivation(user.pk)
                    User.objects.filter(pk=user.pk).update(is_active=False)
                return "changed"
            except ModelValidationError:
                return "protected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(deactivate, users))
        self.assertCountEqual(outcomes, ["changed", "protected"])
