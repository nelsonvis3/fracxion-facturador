"""Authenticate the edge proxy before trusting its client IP and HTTPS scheme."""

from ipaddress import ip_address

from django.conf import settings
from django.http import JsonResponse
from django.utils.crypto import constant_time_compare


class NetlifyProxyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.META.pop("HTTP_X_FORWARDED_PROTO", None)
        supplied = request.META.pop("HTTP_X_FRACXION_PROXY_SECRET", "")
        client_ip = request.META.pop("HTTP_X_FRACXION_CLIENT_IP", "")
        if request.path in {"/health/", "/ready/"} and request.method in {"GET", "HEAD"}:
            return self.get_response(request)
        secret = settings.FRACXION_PROXY_SECRET
        if not secret or not constant_time_compare(supplied, secret):
            return JsonResponse(
                {"detail": "Acceso no disponible."},
                status=403,
                headers={"Cache-Control": "private, no-store"},
            )
        try:
            request.META["REMOTE_ADDR"] = str(ip_address(client_ip))
        except ValueError:
            return JsonResponse({"detail": "Proxy inválido."}, status=400)
        request.META["HTTP_X_FORWARDED_PROTO"] = "https"
        return self.get_response(request)
