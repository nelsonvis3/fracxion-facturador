import base64
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from auditlog.models import AuditEvent

from .invitations import accept_invitation, create_invitation, manage_invitation, token_digest
from .models import BusinessSettings, Membership, Tenant

User = get_user_model()


class EnterpriseFixtures(TestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(name="Enterprise", slug="enterprise")
        self.foreign = Tenant.objects.create(name="Other", slug="other")
        self.owner = User.objects.create_user(
            email="enterprise-owner@example.com", password="SyntheticOwnerPassword2026!"
        )
        self.owner_member = Membership.objects.create(
            tenant=self.tenant, user=self.owner, role="owner"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.base = f"/api/tenants/{self.tenant.pk}"

    def invite(self, email="invitee@example.com", role="viewer"):
        with self.captureOnCommitCallbacks(execute=True):
            invitation = create_invitation(
                tenant_id=self.tenant.pk, actor=self.owner, email=email, role=role
            )
        link = next(line for line in mail.outbox[-1].body.splitlines() if "#token=" in line)
        token = parse_qs(urlsplit(link).fragment)["token"][0]
        return invitation, token


class SettingsSecurityTests(EnterpriseFixtures):
    def test_read_defaults_without_writing_and_update_is_audited(self):
        response = self.client.get(f"{self.base}/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["default_currency"], "ARS")
        self.assertFalse(BusinessSettings.objects.exists())
        response = self.client.patch(
            f"{self.base}/settings/",
            {"name": "Updated", "timezone": "UTC", "payment_terms_days": 30},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Updated")
        self.assertTrue(
            AuditEvent.objects.filter(tenant=self.tenant, entity_type="tenancy.settings").exists()
        )

    def test_settings_matrix_and_cross_tenant_payload(self):
        for role in ["owner", "admin", "accountant", "sales", "viewer"]:
            self.owner_member.role = role
            self.owner_member.save()
            self.assertEqual(self.client.get(f"{self.base}/settings/").status_code, 200)
            self.assertEqual(
                self.client.patch(
                    f"{self.base}/settings/", {"name": "Allowed"}, format="json"
                ).status_code,
                200 if role in {"owner", "admin"} else 403,
            )
        self.owner_member.role = "owner"
        self.owner_member.save()
        self.assertEqual(
            self.client.patch(
                f"{self.base}/settings/",
                {"tenant": str(self.foreign.pk), "name": "Spoof"},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(f"/api/tenants/{self.foreign.pk}/settings/").status_code, 403
        )
        for change in ["member", "tenant", "user"]:
            model = {"member": self.owner_member, "tenant": self.tenant, "user": self.owner}[change]
            model.is_active = False
            model.save()
            self.assertEqual(self.client.get(f"{self.base}/settings/").status_code, 403)
            model.is_active = True
            model.save()
        user = User.objects.create_user(email="unrelated@example.com")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(f"{self.base}/settings/").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"{self.base}/settings/").status_code, 401)

    def test_invalid_values_and_audit_failure_leave_settings_unchanged(self):
        for data in [
            {"timezone": "No/SuchZone"},
            {"country_code": "ZZ"},
            {"default_currency": "ZZZ"},
            {"payment_terms_days": -1},
            {"payment_terms_days": 3651},
            {"website": "javascript:alert(1)"},
        ]:
            self.assertEqual(
                self.client.patch(f"{self.base}/settings/", data, format="json").status_code, 400
            )
        with patch(
            "tenancy.services.record_audit_event", side_effect=RuntimeError("audit unavailable")
        ):
            with self.assertRaises(RuntimeError):
                self.client.patch(f"{self.base}/settings/", {"name": "Rollback"}, format="json")
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.name, "Enterprise")
        self.assertFalse(BusinessSettings.objects.exists())

    def test_logo_is_recoded_private_and_tenant_protected(self):
        image = BytesIO()
        Image.new("RGB", (32, 32), "blue").save(image, format="PNG")
        payload = base64.b64encode(image.getvalue() + b"<script>not an image</script>").decode()
        self.assertEqual(
            self.client.patch(
                f"{self.base}/settings/", {"logo_data": payload}, format="json"
            ).status_code,
            200,
        )
        response = self.client.get(f"{self.base}/settings/logo/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"<script>", response.content)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(
            self.client.get(f"/api/tenants/{self.foreign.pk}/settings/logo/").status_code, 403
        )
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"{self.base}/settings/logo/").status_code, 401)

    def test_logo_rejects_active_content_bad_bytes_and_oversized_dimensions(self):
        large = BytesIO()
        Image.new("RGB", (2049, 1)).save(large, format="PNG")
        for data in [
            b"<svg onload='alert(1)'/>",
            b"not an image",
            large.getvalue(),
            b"x" * (512 * 1024 + 1),
        ]:
            self.assertEqual(
                self.client.patch(
                    f"{self.base}/settings/",
                    {"logo_data": base64.b64encode(data).decode()},
                    format="json",
                ).status_code,
                400,
            )


class InvitationTests(EnterpriseFixtures):
    def test_token_only_in_mail_and_new_user_has_no_platform_privileges(self):
        invitation, token = self.invite()
        self.assertEqual(invitation.token_digest, token_digest(token))
        response = self.client.get(f"{self.base}/invitations/")
        self.assertNotIn(token, str(response.data))
        self.assertNotIn(invitation.token_digest, str(response.data))
        user, member = accept_invitation(
            token=token,
            first_name="Invited",
            password="SyntheticInvitePassword2026!",
            password_confirm="SyntheticInvitePassword2026!",
        )
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(member.tenant, self.tenant)
        self.assertEqual(member.role, "viewer")
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(Tenant.objects.count(), 2)  # no extra company on invitation onboarding
        with self.assertRaises(ValidationError):
            accept_invitation(token=token, actor=user)

    def test_expired_revoked_and_rotated_tokens_are_rejected(self):
        invitation, token = self.invite()
        manage_invitation(tenant_id=self.tenant.pk, actor=self.owner, invitation_id=invitation.pk)
        with self.assertRaises(ValidationError):
            accept_invitation(token=token)
        invitation, token = self.invite("second@example.com")
        with self.captureOnCommitCallbacks(execute=True):
            manage_invitation(
                tenant_id=self.tenant.pk, actor=self.owner, invitation_id=invitation.pk, resend=True
            )
        with self.assertRaises(ValidationError):
            accept_invitation(token=token)
        invitation.refresh_from_db()
        invitation.expires_at = timezone.now() - timedelta(seconds=1)
        invitation.save()
        response = self.client.get(f"{self.base}/invitations/")
        self.assertEqual(response.data["results"][0]["state"], "expired")

    def test_existing_account_must_sign_in_as_recipient(self):
        from rest_framework.exceptions import PermissionDenied

        target = User.objects.create_user(email="invitee@example.com")
        invitation, token = self.invite()
        with self.assertRaises(ValidationError):
            accept_invitation(token=token)
        with self.assertRaises(PermissionDenied):
            accept_invitation(token=token, actor=self.owner)
        user, member = accept_invitation(token=token, actor=target)
        self.assertEqual(user, target)
        self.assertTrue(member.is_active)

    def test_inviter_revoked_or_inactive_company_cannot_grant_access(self):
        invitation, token = self.invite()
        self.owner_member.is_active = False
        self.owner_member.save()
        with self.assertRaises(ValidationError):
            accept_invitation(token=token)
        self.owner_member.is_active = True
        self.owner_member.save()
        self.tenant.is_active = False
        self.tenant.save()
        with self.assertRaises(ValidationError):
            accept_invitation(token=token)

    def test_admin_cannot_invite_privileged_roles_or_modify_them(self):
        self.owner_member.role = "admin"
        self.owner_member.save()
        for role in ["owner", "admin"]:
            self.assertEqual(
                self.client.post(
                    f"{self.base}/invitations/",
                    {"email": "x@example.com", "role": role},
                    format="json",
                ).status_code,
                403,
            )
        self.assertEqual(
            self.client.post(
                f"{self.base}/invitations/",
                {"email": "x@example.com", "role": "accountant", "is_superuser": True},
                format="json",
            ).status_code,
            400,
        )

    def test_invitation_acceptance_is_csrf_protected_and_transactional(self):
        invitation, token = self.invite()
        client = Client(enforce_csrf_checks=True)
        data = {
            "token": token,
            "first_name": "Invited",
            "password": "SyntheticInvitePassword2026!",
            "password_confirm": "SyntheticInvitePassword2026!",
        }
        self.assertEqual(
            client.post(
                "/api/auth/invitations/accept/", data, content_type="application/json"
            ).status_code,
            403,
        )
        csrf = client.get("/api/auth/csrf/").json()["csrfToken"]
        with patch(
            "tenancy.invitations.record_audit_event", side_effect=RuntimeError("audit unavailable")
        ):
            with self.assertRaises(RuntimeError):
                client.post(
                    "/api/auth/invitations/accept/",
                    data,
                    content_type="application/json",
                    HTTP_X_CSRFTOKEN=csrf,
                )
        self.assertFalse(User.objects.filter(email=invitation.email).exists())
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "pending")
        response = client.post(
            "/api/auth/invitations/accept/",
            data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get(f"{self.base}/customers/").status_code, 200)

    def test_delivery_failure_is_visible_and_mail_is_not_sent_before_commit(self):
        with patch("tenancy.invitations.send_mail", side_effect=RuntimeError("smtp")):
            invitation, _ = None, None
            with self.captureOnCommitCallbacks(execute=True):
                invitation = create_invitation(
                    tenant_id=self.tenant.pk,
                    actor=self.owner,
                    email="failure@example.com",
                    role="viewer",
                )
                self.assertFalse(mail.outbox)
        invitation.refresh_from_db()
        self.assertEqual(invitation.delivery_status, "failed")

    def test_team_and_invites_are_isolated_and_permission_checked(self):
        invitation, token = self.invite()
        for role in ["viewer", "sales", "accountant"]:
            self.owner_member.role = role
            self.owner_member.save()
            for resource in ["members", "invitations"]:
                self.assertEqual(self.client.get(f"{self.base}/{resource}/").status_code, 403)
        self.owner_member.role = "owner"
        self.owner_member.save()
        self.assertEqual(
            self.client.post(
                f"/api/tenants/{self.foreign.pk}/invitations/{invitation.pk}/revoke/",
                {},
                format="json",
            ).status_code,
            403,
        )
