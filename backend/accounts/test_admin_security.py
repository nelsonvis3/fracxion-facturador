from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.test import TestCase

from auditlog.models import AuditEvent

User = get_user_model()


class AdminSecurityTests(TestCase):
    def test_malformed_password_target_returns_404_instead_of_500(self):
        self.client.force_login(self.root)
        self.client.raise_request_exception = False
        for target in ["not-an-integer", "999999999999999999999999", "9223372036854775807"]:
            response = self.client.post(f"/admin/accounts/user/{target}/password/", {})
            self.assertEqual(response.status_code, 404)
        self.assertFalse(
            AuditEvent.objects.filter(metadata__event="admin_password_changed").exists()
        )

    def setUp(self):
        cache.clear()
        self.root = User.objects.create_superuser(
            email="root-admin@example.com", password="SyntheticRootPass2026!"
        )
        self.limited = User.objects.create_user(
            email="limited-admin@example.com", is_staff=True, password="SyntheticLimitedPass2026!"
        )
        self.limited.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="accounts",
                codename__in=["view_user", "change_user", "add_user"],
            )
        )
        self.target = User.objects.create_user(
            email="regular-admin-target@example.com", password="SyntheticTargetPass2026!"
        )

    def data(self, user, **extra):
        return {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": "on",
            "date_joined_0": "2026-10-14",
            "date_joined_1": "12:00:00",
            "_save": "Save",
            **extra,
        }

    def test_limited_staff_cannot_read_edit_or_change_privileged_passwords(self):
        self.client.force_login(self.limited)
        index = self.client.get("/admin/accounts/user/")
        self.assertNotContains(index, self.root.email)
        for target in [self.root, self.limited]:
            response = self.client.post(
                f"/admin/accounts/user/{target.pk}/change/",
                self.data(target, email="takeover@example.com", is_superuser="on"),
            )
            self.assertIn(response.status_code, {302, 403, 404})
            response = self.client.post(
                f"/admin/accounts/user/{target.pk}/password/",
                {
                    "password1": "SyntheticTakeoverPass2026!",
                    "password2": "SyntheticTakeoverPass2026!",
                },
            )
            self.assertIn(response.status_code, {302, 403, 404})
            target.refresh_from_db()
            self.assertNotEqual(target.email, "takeover@example.com")
            self.assertFalse(target.check_password("SyntheticTakeoverPass2026!"))

    def test_forged_flags_and_groups_do_not_promote_regular_user(self):
        group = Group.objects.create(name="Synthetic platform group")
        group.permissions.set(Permission.objects.filter(content_type__app_label="accounts"))
        self.client.force_login(self.limited)
        response = self.client.post(
            f"/admin/accounts/user/{self.target.pk}/change/",
            self.data(
                self.target,
                first_name="Edited",
                is_staff="on",
                is_superuser="on",
                groups=[str(group.pk)],
                user_permissions=[str(p.pk) for p in self.limited.user_permissions.all()],
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertEqual(self.target.first_name, "Edited")
        self.assertFalse(self.target.is_staff)
        self.assertFalse(self.target.is_superuser)
        self.assertFalse(self.target.groups.exists())
        self.assertFalse(self.target.user_permissions.exists())

    def test_superuser_sensitive_changes_are_audited_without_password_material(self):
        group = Group.objects.create(name="Synthetic audit group")
        self.client.force_login(self.root)
        response = self.client.post(
            f"/admin/accounts/user/{self.target.pk}/change/",
            self.data(self.target, email="updated-target@example.com", groups=[str(group.pk)]),
        )
        self.assertEqual(response.status_code, 302)
        events = AuditEvent.objects.filter(
            entity_type="accounts.user", entity_id=str(self.target.pk)
        )
        self.assertTrue(any("email" in event.changes.get("fields", {}) for event in events))
        self.assertTrue(any("groups" in event.changes.get("fields", {}) for event in events))
        response = self.client.post(
            f"/admin/accounts/user/{self.target.pk}/password/",
            {"password1": "SyntheticUpdatedPass2026!", "password2": "SyntheticUpdatedPass2026!"},
        )
        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password("SyntheticUpdatedPass2026!"))
        event = events.get(metadata__event="admin_password_changed")
        self.assertNotIn("SyntheticUpdatedPass", str(event.metadata))
        self.assertEqual(event.changes, {})

    def test_user_delete_is_denied_even_for_superuser(self):
        self.client.force_login(self.root)
        self.assertEqual(
            self.client.post(
                f"/admin/accounts/user/{self.target.pk}/delete/", {"post": "yes"}
            ).status_code,
            403,
        )
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())

    def test_stale_admin_form_does_not_restore_old_security_state(self):
        import uuid
        from types import SimpleNamespace

        from django.contrib import admin
        from django.test import RequestFactory
        from django.utils import timezone

        from .admin import UserAdmin

        stale = User.objects.get(pk=self.target.pk)
        nonce = uuid.uuid4()
        at = timezone.now()
        User.objects.filter(pk=self.target.pk).update(
            session_version=7,
            email_verification_nonce=nonce,
            verified_email=self.target.email,
            email_verified_at=at,
        )
        stale.first_name = "Updated profile"
        request = RequestFactory().post("/admin/accounts/user/change/")
        request.user = self.root
        UserAdmin(User, admin.site).save_model(
            request, stale, SimpleNamespace(changed_data=["first_name"]), True
        )
        self.target.refresh_from_db()
        self.assertEqual(self.target.first_name, "Updated profile")
        self.assertEqual(self.target.session_version, 7)
        self.assertEqual(self.target.email_verification_nonce, nonce)
        self.assertEqual(self.target.email_verified_at, at)
        self.assertTrue(self.target.is_email_verified)

    def test_stale_admin_password_form_only_writes_password(self):
        from .admin import AccountPasswordChangeForm

        stale = User.objects.get(pk=self.target.pk)
        User.objects.filter(pk=stale.pk).update(session_version=9)
        form = AccountPasswordChangeForm(
            stale,
            data={
                "password1": "SyntheticNewAdminPassword2026!",
                "password2": "SyntheticNewAdminPassword2026!",
                "usable_password": "true",
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password("SyntheticNewAdminPassword2026!"))
        self.assertEqual(self.target.session_version, 9)
