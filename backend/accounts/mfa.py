"""Explicit, transactional MFA shared by API login and Django Admin.

Lock order: User (NO KEY UPDATE), then its AccountMFA. No secret enters audit.
The encrypted seed and encryption key must be backed up separately.
"""

import base64
import re
import secrets
import time
from datetime import timedelta
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django_otp.oath import TOTP

from .models import AccountMFA
from .security import security_event

PROOF = "account_mfa_generation"
CHALLENGE = "account_mfa_challenge"


def cipher():
    if not settings.MFA_ENCRYPTION_KEYS:
        raise ImproperlyConfigured("Configure MFA_ENCRYPTION_KEYS before enrolling MFA.")
    return MultiFernet([Fernet(key) for key in settings.MFA_ENCRYPTION_KEYS])


def secret_bytes(device):
    return cipher().decrypt(device.encrypted_secret.encode())


def lock_user(user_id):
    return (
        get_user_model()
        .objects.select_for_update(no_key=True)
        .filter(pk=user_id, is_active=True)
        .first()
    )


def lock_device(user):
    return AccountMFA.objects.select_for_update().filter(user=user).first()


def verify(device, token, *, recovery=True):
    """Caller holds both locks; accepted time steps/codes are consumed atomically."""
    if not isinstance(token, str) or len(token) > 64:
        return False
    if re.fullmatch(r"[0-9]{6}", token):
        totp = TOTP(secret_bytes(device))
        if totp.verify(int(token), tolerance=1, min_t=device.last_t + 1):
            device.last_t = totp.t()
            device.save(update_fields=["last_t"])
            return True
    elif recovery and re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{8}", token):
        # A bounded list; no plaintext recovery credential is persisted.
        for index, hashed in enumerate(device.recovery_hashes):
            if check_password(token, hashed):
                device.recovery_hashes.pop(index)
                device.save(update_fields=["recovery_hashes"])
                return True
    return False


def recovery_codes(device):
    codes = [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(8)]
    device.recovery_hashes = [make_password(code) for code in codes]
    device.save(update_fields=["recovery_hashes"])
    return codes


def setup(user):
    secret = secrets.token_bytes(20)
    device, _ = AccountMFA.objects.update_or_create(
        user=user,
        defaults={
            "encrypted_secret": cipher().encrypt(secret).decode(),
            "setup_expires_at": timezone.now() + timedelta(minutes=10),
            "confirmed_at": None,
            "last_t": -1,
            "recovery_hashes": [],
        },
    )
    text = base64.b32encode(secret).decode()
    uri = (
        "otpauth://totp/"
        + quote(f"Fracxion:{user.email}", safe="")
        + "?"
        + urlencode(
            {
                "secret": text,
                "issuer": "Fracxion",
                "algorithm": "SHA1",
                "digits": 6,
                "period": 30,
            }
        )
    )
    return device, text, uri


def refresh_sessions(request, user, device):
    user.session_version += 1
    user.save(update_fields=["session_version"])
    update_session_auth_hash(request, user)
    Session.objects.filter(account_record__user=user).exclude(
        session_key=request.session.session_key
    ).delete()
    if device:
        request.session[PROOF] = str(device.generation)
    else:
        request.session.pop(PROOF, None)


def start_challenge(request, user, device):
    # Remove any previous identity; a password alone never authenticates this session.
    logout(request)
    request.session[CHALLENGE] = {
        "user": user.pk,
        "hash": user.get_session_auth_hash(),
        "generation": str(device.generation),
        "created": time.time(),
    }
    request.session.set_expiry(300)


def complete_login(request, user, device=None):
    request.session.pop(CHALLENGE, None)
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    if device:
        request.session[PROOF] = str(device.generation)
    security_event(request, event="login", outcome="success", actor=user)


@transaction.atomic
def challenge_user(request, token):
    challenge = request.session.get(CHALLENGE)
    if not isinstance(challenge, dict) or not 0 <= time.time() - challenge.get("created", 0) <= 300:
        return None
    user = lock_user(challenge["user"])
    if user is None or not constant_time_compare(user.get_session_auth_hash(), challenge["hash"]):
        return None
    device = lock_device(user)
    if not device or not device.confirmed_at or str(device.generation) != challenge["generation"]:
        return None
    if not verify(device, token):
        return None
    complete_login(request, user, device)
    return user
