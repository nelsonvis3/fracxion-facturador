from django.contrib import admin

from config.admin import ReadOnlyBusinessAdmin

from .models import Invoice, InvoiceLine, Payment, PaymentReversal


@admin.register(Invoice)
class InvoiceAdmin(ReadOnlyBusinessAdmin):
    list_display = ("id", "tenant", "internal_number", "status", "currency", "total")
    list_filter = ("status", "currency", "tenant")


admin.site.register(InvoiceLine, ReadOnlyBusinessAdmin)
admin.site.register(Payment, ReadOnlyBusinessAdmin)
admin.site.register(PaymentReversal, ReadOnlyBusinessAdmin)
