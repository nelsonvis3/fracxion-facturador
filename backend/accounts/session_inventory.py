"""Session metadata never exposes the Django credential to application JSON."""

import logging
from datetime import timedelta
from ipaddress import ip_address

from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from .models import AccountSession

logger = logging.getLogger(__name__)


def describe_device(user_agent):
    agent = user_agent.lower()
    browser = (
        "Firefox"
        if "firefox" in agent
        else "Edge"
        if "edg/" in agent
        else "Chrome / Chromium"
        if "chrome" in agent
        else "Safari"
        if "safari" in agent
        else "Otro navegador"
    )
    platform = (
        "Android"
        if "android" in agent
        else "iOS"
        if any(name in agent for name in ["iphone", "ipad"])
        else "Windows"
        if "windows" in agent
        else "macOS"
        if "macintosh" in agent
        else "Linux"
        if "linux" in agent
        else "Sistema no identificado"
    )
    return f"{browser} · {platform}"


class SessionInventoryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(("/api/", "/admin/")):
            return self.get_response(request)
        before = (getattr(request.user, "pk", None), request.session.session_key)
        self.capture(request)
        response = self.get_response(request)
        after = (getattr(request.user, "pk", None), request.session.session_key)
        if after != before and response.status_code < 400:
            self.capture(request)
        return response

    def capture(self, request):
        user = getattr(request, "user", None)
        key = request.session.session_key
        if not getattr(user, "is_authenticated", False) or not user.is_active or not key:
            return
        try:
            existing = (
                AccountSession.objects.filter(session_id=key, user=user)
                .only("pk", "last_seen")
                .first()
            )
            if existing:
                cutoff = timezone.now() - timedelta(minutes=5)
                if existing.last_seen < cutoff:
                    AccountSession.objects.filter(pk=existing.pk, last_seen__lt=cutoff).update(
                        last_seen=timezone.now()
                    )
                return
            with transaction.atomic():
                # Never save/recreate the session: it may have been revoked concurrently.
                if not Session.objects.filter(
                    session_key=key, expire_date__gt=timezone.now()
                ).exists():
                    return
                try:
                    address = str(ip_address(request.META.get("REMOTE_ADDR", "")))
                except ValueError:
                    address = None
                record, created = AccountSession.objects.get_or_create(
                    session_id=key,
                    defaults={
                        "user": user,
                        "last_seen": timezone.now(),
                        "device": describe_device(request.META.get("HTTP_USER_AGENT", "")[:512]),
                        "ip_address": address,
                    },
                )
                if record.user_id != user.pk:
                    logger.error("Inconsistencia de propietario en inventario de sesiones.")
                    return
                if not created:
                    AccountSession.objects.filter(
                        pk=record.pk, last_seen__lt=timezone.now() - timedelta(minutes=5)
                    ).update(last_seen=timezone.now())
        except Exception:
            # Metadata failure does not change Django's authentication or revocation checks.
            logger.error("No se pudo actualizar el inventario de sesiones.")
        return
