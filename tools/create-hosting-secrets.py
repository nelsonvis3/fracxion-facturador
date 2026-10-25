"""Create private deployment secrets without printing or overwriting them."""

import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

destination = Path(__file__).resolve().parents[1] / ".env.hosting-secrets"
descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w") as output:
    output.write(f"DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}\n")
    output.write(f"MFA_ENCRYPTION_KEYS={Fernet.generate_key().decode()}\n")
print("Created .env.hosting-secrets with mode 600. Values were not printed.")
