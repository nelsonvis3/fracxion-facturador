from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


def csrf_failure(request, reason=""):
    return JsonResponse(
        {
            "detail": "No se pudo validar la protección CSRF. Actualizá la página.",
            "code": "csrf_failed",
        },
        status=403,
    )


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        cache.set("readiness", True, timeout=10)
        if not cache.get("readiness"):
            raise RuntimeError("Cache unavailable")
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
