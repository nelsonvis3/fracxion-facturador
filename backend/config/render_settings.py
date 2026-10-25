"""Render + Netlify profile; use only with the authenticated Netlify edge proxy."""

import os

from django.core.exceptions import ImproperlyConfigured

# Render injects this exact hostname; never accept wildcard hosts.
if hostname := os.getenv("RENDER_EXTERNAL_HOSTNAME"):
    os.environ.setdefault("DJANGO_ALLOWED_HOSTS", hostname)

from .settings import *  # noqa: E402,F403

if not PRODUCTION or not MFA_ENCRYPTION_KEYS:  # noqa: F405
    raise ImproperlyConfigured("Render requiere producción y MFA_ENCRYPTION_KEYS.")

FRACXION_PROXY_SECRET = os.getenv("FRACXION_PROXY_SECRET", "")
if len(FRACXION_PROXY_SECRET) < 32:
    raise ImproperlyConfigured(
        "FRACXION_PROXY_SECRET debe tener al menos 32 caracteres aleatorios."
    )

MIDDLEWARE = [
    "config.render_proxy.NetlifyProxyMiddleware"
    if item == "config.middleware.TrustedProxyMiddleware"
    else item
    for item in MIDDLEWARE  # noqa: F405
]
# Only the authenticated middleware can set this header. Public health endpoints
# bypass HTTPS redirection in the base settings and never authenticate a session.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
