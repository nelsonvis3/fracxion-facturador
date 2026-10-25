from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from config import schema  # noqa: F401

        from .mfa_admin import remember_admin_mfa

        user_logged_in.connect(remember_admin_mfa, dispatch_uid="accounts.remember_admin_mfa")
