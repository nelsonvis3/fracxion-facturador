from ipaddress import ip_address, ip_network

from django.conf import settings


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
