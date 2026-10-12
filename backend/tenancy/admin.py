from django.contrib import admin

from .models import Membership, Tenant


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)
    inlines = (MembershipInline,)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("tenant", "user", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("tenant__name", "user__email")
    autocomplete_fields = ("tenant", "user")
