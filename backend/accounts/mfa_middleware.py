from django.contrib.auth import logout

from .mfa import PROOF
from .models import AccountMFA


class MFASessionMiddleware:
    """Reject a session established outside the verified MFA login flows."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            generation = (
                AccountMFA.objects.filter(user=request.user, confirmed_at__isnull=False)
                .values_list("generation", flat=True)
                .first()
            )
            if generation and request.session.get(PROOF) != str(generation):
                logout(request)
        return self.get_response(request)
