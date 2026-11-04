"""Synthetic browser fixture only: issues a fresh signup code and prints it."""

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

from accounts.signup_code import issue_code  # noqa: E402

if (
    settings.DATABASES["default"]["NAME"] != "test_facturador_e2e"
    or settings.EMAIL_BACKEND != "django.core.mail.backends.locmem.EmailBackend"
):
    raise SystemExit("Requires synthetic database and memory mail backend")
user = get_user_model().objects.get(
    email=sys.argv[1], email__endswith="@e2e.example", is_active=True
)
print(issue_code(user))
