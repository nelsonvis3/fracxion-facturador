"""Datos sintéticos para E2E. Rechaza bases que no sean explícitamente de pruebas."""

import json
import os
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if os.getenv("DJANGO_SETTINGS_MODULE") not in {"config.test_settings", "config.e2e_settings"}:
    raise RuntimeError("Se requiere una configuración de pruebas explícita.")

import django

django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.management import call_command
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from tenancy.models import Membership, Tenant

if not settings.DATABASES["default"]["NAME"].startswith("test_"):
    raise RuntimeError("Se requiere una base cuyo nombre empiece con test_.")

call_command("migrate", verbosity=0)
tenant, _ = Tenant.objects.get_or_create(
    id=UUID("00000000-0000-4000-8000-000000000001"), defaults={"name": "Empresa E2E", "slug": "e2e"}
)
for role in ["owner", "viewer", "accountant"]:
    user, _ = get_user_model().objects.get_or_create(
        email=f"{role}@e2e.example", defaults={"first_name": "Prueba"}
    )
    user.set_password("SyntheticE2EPassword2026!")
    user.save()
    Membership.objects.update_or_create(
        user=user, tenant=tenant, defaults={"role": role, "is_active": True}
    )
nameless_user, _ = get_user_model().objects.get_or_create(email="nameless@e2e.example")
nameless_user.first_name = ""
nameless_user.last_name = ""
nameless_user.set_password("SyntheticE2EPassword2026!")
nameless_user.save()
Membership.objects.update_or_create(
    user=nameless_user,
    tenant=tenant,
    defaults={"role": "viewer", "is_active": True},
)
reset_user, _ = get_user_model().objects.get_or_create(email="reset@e2e.example")
reset_user.set_password("SyntheticE2EPassword2026!")
reset_user.save()
fixture = {
    "uid": urlsafe_base64_encode(force_bytes(reset_user.pk)),
    "token": default_token_generator.make_token(reset_user),
}
Path(__file__).resolve().parents[2].joinpath("frontend/e2e/reset-fixture.json").write_text(
    json.dumps(fixture)
)
print("Datos sintéticos E2E preparados.")

# Invitation onboarding uses another controlled token, never returned by production APIs.
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from django.core import mail

from tenancy.invitations import create_invitation

invited_email = f"invited.{uuid4().hex[:10]}@e2e.example"
create_invitation(
    tenant_id=tenant.pk,
    actor=get_user_model().objects.get(email="owner@e2e.example"),
    email=invited_email,
    role="viewer",
)
invitation_link = next(line for line in mail.outbox[-1].body.splitlines() if "#token=" in line)
invitation_fixture = {
    "token": parse_qs(urlsplit(invitation_link).fragment)["token"][0],
    "email": invited_email,
    "tenant": str(tenant.pk),
}
Path(__file__).resolve().parents[2].joinpath("frontend/e2e/invitation-fixture.json").write_text(
    json.dumps(invitation_fixture)
)
