from django.contrib import admin


class ReadOnlyBusinessAdmin(admin.ModelAdmin):
    """Las operaciones de negocio pasan por la API para conservar la auditoría."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
