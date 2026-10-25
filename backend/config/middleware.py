import logging
from ipaddress import ip_address, ip_network

from django.conf import settings

logger = logging.getLogger(__name__)


class TrustedProxyMiddleware:
    """Acota la IP del cliente a una cabecera reescrita por un proxy conocido."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.networks = [ip_network(network) for network in settings.TRUSTED_PROXY_NETWORKS]

    def __call__(self, request):
        try:
            observed = ip_address(request.META.get("REMOTE_ADDR", ""))
            trusted = any(observed in network for network in self.networks)
        except ValueError:
            trusted = False
        if trusted:
            try:
                client_ip = ip_address(request.META.get("HTTP_X_CLIENT_IP", ""))
                request.META["REMOTE_ADDR"] = str(client_ip)
            except ValueError:
                pass
        else:
            request.META.pop("HTTP_X_FORWARDED_PROTO", None)
        return self.get_response(request)


class PrivateResponseMiddleware:
    """Impide almacenar respuestas de API privadas en proxies o navegadores."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "private, no-store"
        return response


class SecurityEventsMiddleware:
    """Protect the platform login and bound logging of rejected requests."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from accounts.rate_limits import is_rate_limited, rate_limit_response
        from accounts.security import security_event
        from auditlog.models import AuditEvent
        from auditlog.services import record_audit_event

        admin_login = request.path == "/admin/login/" and request.method == "POST"
        if admin_login:
            identity = request.POST.get("username", "")[:254].strip().lower()
            if is_rate_limited(request, action="admin-login", limit=10) or (
                identity
                and is_rate_limited(request, action="admin-account", limit=10, identity=identity)
            ):
                return rate_limit_response()
        admin_logout_actor = (
            request.user
            if request.path == "/admin/logout/" and request.user.is_authenticated
            else None
        )
        response = self.get_response(request)
        try:
            if request.path in {
                "/api/auth/password/change/",
                "/api/auth/sessions/revoke-others/",
            } and response.status_code in {400, 429}:
                if not is_rate_limited(request, action="account-denial-audit", limit=20):
                    security_event(
                        request,
                        event="sensitive_account_change",
                        outcome="rejected",
                        actor=request.user,
                    )
            if admin_login and response.status_code < 400:
                actor = (
                    request.user
                    if request.user.is_authenticated and request.user.is_staff
                    else None
                )
                security_event(
                    request, event="login", outcome="success" if actor else "rejected", actor=actor
                )
            if admin_logout_actor and request.method == "POST" and response.status_code < 400:
                security_event(request, event="logout", outcome="success", actor=admin_logout_actor)
            if request.path.startswith("/api/") and response.status_code in {401, 403}:
                if not is_rate_limited(request, action="audit-denial", limit=20):
                    record_audit_event(
                        action=AuditEvent.Action.PERMISSION_DENIED,
                        entity_type="accounts.security",
                        request=request,
                        metadata={
                            "event": "access_denied",
                            "status": response.status_code,
                            "method": request.method,
                        },
                    )
        except Exception:
            # A logging outage must never allow a rejected request or prevent logout.
            logger.error("No se pudo persistir un evento de seguridad.")
        return response
