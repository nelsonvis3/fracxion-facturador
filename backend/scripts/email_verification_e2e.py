"""Synthetic browser fixture only; never exposes tokens through an HTTP endpoint."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if os.environ.get("DJANGO_SETTINGS_MODULE") != "config.e2e_settings":
    raise SystemExit("Requires isolated E2E settings")

import django

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402

from accounts.email_verification import verification_token  # noqa: E402

if (
    settings.DATABASES["default"]["NAME"] != "test_facturador_e2e"
    or settings.EMAIL_BACKEND != "django.core.mail.backends.locmem.EmailBackend"
):
    raise SystemExit("Requires synthetic database and memory mail backend")
user = get_user_model().objects.get(
    pk=int(sys.argv[1]), email__endswith="@e2e.example", is_active=True
)
print(verification_token(user))
