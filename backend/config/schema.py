from drf_spectacular.authentication import SessionScheme
from rest_framework import serializers


class SessionAuthenticationScheme(SessionScheme):
    target_class = "accounts.authentication.SessionAuthentication"


class ReferenceOptionSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class ReferenceListSerializer(serializers.Serializer):
    results = ReferenceOptionSerializer(many=True)


class TenantOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    role = serializers.ChoiceField(choices=["owner", "admin", "accountant", "sales", "viewer"])


class TenantListSerializer(serializers.Serializer):
    results = TenantOptionSerializer(many=True)
