"""Six-digit email code that an account must confirm before its first session."""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .security import security_event

logger = logging.getLogger(__name__)
CODE_TTL = timedelta(minutes=15)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5


def code_hash(user, code):
    # The salt ties a code to its account, so a leaked hash cannot be replayed elsewhere.
    return salted_hmac(f"accounts.signup_code:{user.pk}", code).hexdigest()


def issue_code(user, *, now=None):
    """Store a fresh code on a locked or just-created user and return it in clear text."""
    now = now or timezone.now()
    code = f"{secrets.randbelow(1_000_000):06d}"
    user.email_code_hash = code_hash(user, code)
    user.email_code_expires_at = now + CODE_TTL
    user.email_code_sent_at = now
    user.email_code_attempts = 0
    user.save(
        update_fields=[
            "email_code_hash",
            "email_code_expires_at",
            "email_code_sent_at",
            "email_code_attempts",
        ]
    )
    return code


def deliver_code(request, user, code):
    """Send outside the transaction; returns False instead of raising so signup still succeeds."""
    try:
        sent = send_mail(
            f"Tu código de Fracxion: {code}",
            f"Tu código para confirmar la cuenta es:\n\n{code}\n\n"
            "Vence en 15 minutos. Si no creaste una cuenta en Fracxion, ignorá este correo.",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        if sent != 1:
            raise RuntimeError("email_not_accepted")
    except Exception:
        security_event(request, event="signup_code_delivery", outcome="failed", actor=user)
        logger.exception(
            "signup_code_delivery_failed",
            extra={"request_id": getattr(request, "request_id", "")},
        )
        return False
    security_event(
        request, event="signup_code_delivery", outcome="accepted_by_transport", actor=user
    )
    return True


def send_new_code(request, user_id, *, force=False):
    """Issue and send a code unless one was sent during the cooldown. Returns False on failure."""
    with transaction.atomic():
        user = (
            get_user_model()
            .objects.select_for_update(no_key=True)
            .filter(pk=user_id, is_active=True)
            .first()
        )
        if user is None or user.is_email_verified:
            return True
        now = timezone.now()
        if (
            not force
            and user.email_code_sent_at
            and now - user.email_code_sent_at < RESEND_COOLDOWN
        ):
            return True
        code = issue_code(user, now=now)
    return deliver_code(request, user, code)


def confirm_code(email, code):
    """Return the verified user, or None for any wrong, expired or exhausted code."""
    with transaction.atomic():
        user = (
            get_user_model()
            .objects.select_for_update(no_key=True)
            .filter(email=email, is_active=True)
            .first()
        )
        if (
            user is None
            or user.is_email_verified
            or not user.email_code_hash
            or not user.email_code_expires_at
            or user.email_code_expires_at <= timezone.now()
            or user.email_code_attempts >= MAX_ATTEMPTS
        ):
            return None
        if not constant_time_compare(user.email_code_hash, code_hash(user, code)):
            user.email_code_attempts += 1
            user.save(update_fields=["email_code_attempts"])
            return None
        user.verified_email = user.email
        user.email_verified_at = timezone.now()
        user.email_code_hash = ""
        user.email_code_expires_at = None
        user.email_code_attempts = 0
        user.save(
            update_fields=[
                "verified_email",
                "email_verified_at",
                "email_code_hash",
                "email_code_expires_at",
                "email_code_attempts",
            ]
        )
        return user
