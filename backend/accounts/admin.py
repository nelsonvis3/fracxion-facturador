from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from django.db import transaction
from django.http import Http404

from auditlog.models import AuditEvent
from auditlog.services import record_audit_event
from tenancy.services import guard_user_deactivation

from .models import User


class AccountCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email",)


class AccountChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

    def clean(self):
        data = super().clean()
        if self.instance.pk and data.get("is_active") is False:
            guard_user_deactivation(self.instance.pk)
        return data


class AccountPasswordChangeForm(AdminPasswordChangeForm):
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save(update_fields=["password"])
        return user


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = AccountCreationForm
    form = AccountChangeForm
    change_password_form = AccountPasswordChangeForm
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("first_name", "last_name")}),
        (
            "Acceso",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Actividad", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"fields": ("email", "password1", "password2")}),)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        query = super().get_queryset(request)
        # Changing a privileged account's password or email would grant its access.
        return (
            query if request.user.is_superuser else query.filter(is_staff=False, is_superuser=False)
        )

    def has_change_permission(self, request, obj=None):
        if obj and not request.user.is_superuser and (obj.is_staff or obj.is_superuser):
            return False
        return super().has_change_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return (
            fields
            if request.user.is_superuser
            else (*fields, "is_staff", "is_superuser", "groups", "user_permissions")
        )

    def save_model(self, request, obj, form, change):
        fields = ("email", "is_active", "is_staff", "is_superuser")
        before = User.objects.filter(pk=obj.pk).values(*fields).first() if change else None
        form.security_relations_before = {
            field: list(getattr(obj, field).values_list("pk", flat=True)) if change else []
            for field in ("groups", "user_permissions")
        }
        if change:
            # A form loaded before session revocation/email verification must not
            # overwrite the security fields (or last_login) with its old snapshot.
            concrete = {field.name for field in obj._meta.concrete_fields if not field.primary_key}
            changed = set(form.changed_data) & concrete
            if changed:
                obj.save(update_fields=changed)
        else:
            super().save_model(request, obj, form, change)
        changes = {
            k: {"before": before[k] if before else None, "after": getattr(obj, k)}
            for k in fields
            if not before or before[k] != getattr(obj, k)
        }
        if changes:
            record_audit_event(
                action=AuditEvent.Action.UPDATE if change else AuditEvent.Action.CREATE,
                entity_type="accounts.user",
                entity_id=str(obj.pk),
                actor=request.user,
                request=request,
                changes={"fields": changes},
            )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        changes = {}
        for field, before in form.security_relations_before.items():
            after = list(getattr(form.instance, field).values_list("pk", flat=True))
            if set(before) != set(after):
                changes[field] = {"before": sorted(before), "after": sorted(after)}
        if changes:
            record_audit_event(
                action=AuditEvent.Action.UPDATE,
                entity_type="accounts.user",
                entity_id=str(form.instance.pk),
                actor=request.user,
                request=request,
                changes={"fields": changes},
            )

    @transaction.atomic
    def user_change_password(self, request, id, form_url=""):
        # Serialize with account security services before Django loads the form.
        try:
            target_id = int(id)
            if not 0 < target_id <= 9223372036854775807:
                raise ValueError()
        except (ValueError, TypeError):
            raise Http404 from None
        target = (
            self.get_queryset(request).select_for_update(no_key=True).filter(pk=target_id).first()
        )
        if target is None:
            raise Http404
        response = super().user_change_password(request, id, form_url)
        if request.method == "POST" and response.status_code == 302:
            from django.contrib.sessions.models import Session

            Session.objects.filter(account_record__user_id=id).exclude(
                session_key=request.session.session_key
            ).delete()
            record_audit_event(
                action=AuditEvent.Action.UPDATE,
                entity_type="accounts.user",
                entity_id=str(id),
                actor=request.user,
                request=request,
                metadata={"event": "admin_password_changed"},
            )
        return response
