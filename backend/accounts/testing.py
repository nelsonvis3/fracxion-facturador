"""Test helpers only: accounts that already confirmed their signup code."""

from django.contrib.auth import get_user_model
from django.utils import timezone


def create_verified_user(**fields):
    user = get_user_model().objects.create_user(**fields)
    user.verified_email = user.email
    user.email_verified_at = timezone.now()
    user.save(update_fields=["verified_email", "email_verified_at"])
    return user
