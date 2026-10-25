"""Límites de autenticación compartidos entre workers mediante Redis."""

import hashlib

from django.core.cache import cache
from django.http import JsonResponse

RATE_WINDOW = 15 * 60


def is_rate_limited(request, *, action, limit, identity=None):
    # El proxy debe establecer REMOTE_ADDR. No confiar en X-Forwarded-For.
    identity = identity or request.META.get("REMOTE_ADDR", "unknown")
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    key = f"auth:{action}:{digest}"
    if cache.add(key, 1, timeout=RATE_WINDOW):
        return False
    try:
        attempts = cache.incr(key)
    except ValueError:
        # Puede expirar entre add e incr. Volver a competir por la clave.
        if cache.add(key, 1, timeout=RATE_WINDOW):
            return False
        attempts = cache.incr(key)
    return attempts > limit


def rate_limit_response():
    response = JsonResponse(
        {"detail": "Demasiados intentos. Volvé a intentarlo más tarde."},
        status=429,
    )
    response["Retry-After"] = str(RATE_WINDOW)
    return response
