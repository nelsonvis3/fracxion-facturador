from django_filters import rest_framework as filters

from .models import Payment


class PaymentFilter(filters.FilterSet):
    invoice = filters.UUIDFilter()

    class Meta:
        model = Payment
        fields = ["invoice", "method"]
