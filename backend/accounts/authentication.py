from rest_framework.authentication import SessionAuthentication as DRFSessionAuthentication


class SessionAuthentication(DRFSessionAuthentication):
    """La ausencia de sesión es 401; un rol insuficiente sigue siendo 403."""

    def authenticate_header(self, request):
        return "Session"
