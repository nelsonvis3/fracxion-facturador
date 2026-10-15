from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import APIException

from auditlog.models import AuditEvent
from auditlog.services import record_audit_event

from .models import Membership, Tenant
from .services import change_member, check_last_owner


class MembershipForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = "__all__"

    def clean(self):
        data = super().clean()
        target = data.get("user")
        target_id = (
            self.instance.user_id
            if not self.instance._state.adding
            else (target.pk if target else None)
        )
        if target_id:
            get_user_model().objects.select_for_update(no_key=True).get(pk=target_id)
        if target is not None and data.get("is_active") and not target.is_active:
            raise forms.ValidationError(
                "No se puede activar una membresía de una cuenta desactivada."
            )
        if not self.instance._state.adding:
            Tenant.objects.select_for_update().get(pk=self.instance.tenant_id)
            before = Membership.objects.select_related("user").get(pk=self.instance.pk)
            if data.get("is_active") and not before.user.is_active:
                raise forms.ValidationError(
                    "No se puede activar una membresía de una cuenta desactivada."
                )
            try:
                check_last_owner(
                    before,
                    role=data.get("role", before.role),
                    is_active=data.get("is_active", before.is_active),
                )
            except APIException as exc:
                raise forms.ValidationError(str(exc.detail)) from exc
        return data


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    fields = ("user", "role", "is_active")
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)
    inlines = (MembershipInline,)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        fields = ("name", "slug", "legal_name", "tax_id", "is_active")
        before = (
            Tenant.objects.select_for_update().filter(pk=obj.pk).values(*fields).first()
            if change
            else None
        )
        super().save_model(request, obj, form, change)
        changes = {
            k: {"before": before[k] if before else None, "after": getattr(obj, k)}
            for k in fields
            if not before or before[k] != getattr(obj, k)
        }
        if changes:
            record_audit_event(
                action=AuditEvent.Action.UPDATE if change else AuditEvent.Action.CREATE,
                entity_type="tenancy.tenant",
                entity_id=str(obj.pk),
                tenant=obj,
                actor=request.user,
                request=request,
                changes={"fields": changes},
            )


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    form = MembershipForm
    list_display = ("tenant", "user", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("tenant__name", "user__email")
    autocomplete_fields = ("tenant", "user")

    def get_readonly_fields(self, request, obj=None):
        return ("tenant", "user") if obj else ()

    def has_delete_permission(self, request, obj=None):
        return False

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if change:
            member = change_member(
                tenant_id=obj.tenant_id,
                member_id=obj.pk,
                actor=request.user,
                role=obj.role,
                is_active=obj.is_active,
                request=request,
                platform=True,
            )
            obj.__dict__.update(member.__dict__)
        else:
            get_user_model().objects.select_for_update(no_key=True).get(pk=obj.user_id)
            Tenant.objects.select_for_update().get(pk=obj.tenant_id)
            super().save_model(request, obj, form, change)
            record_audit_event(
                action=AuditEvent.Action.CREATE,
                entity_type="tenancy.membership",
                entity_id=str(obj.pk),
                tenant=obj.tenant,
                actor=request.user,
                request=request,
                changes={
                    "fields": {
                        "role": {"before": None, "after": obj.role},
                        "is_active": {"before": None, "after": obj.is_active},
                    }
                },
            )
