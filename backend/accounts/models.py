import uuid

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.crypto import salted_hmac


class UserManager(BaseUserManager):
    """Manager personalizado con email como identificador."""

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email or not email.strip():
            raise ValueError("El correo electrónico es obligatorio.")

        email = email.strip().lower()

        user = self.model(
            email=email,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Un superusuario debe tener is_staff=True.")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Un superusuario debe tener is_superuser=True.")

        if not password:
            raise ValueError("Un superusuario debe tener una contraseña.")

        return self.create_user(
            email=email,
            password=password,
            **extra_fields,
        )


class User(AbstractUser):
    """Usuario de la plataforma SaaS."""

    username = None

    email = models.EmailField(
        "correo electrónico",
        unique=True,
    )
    session_version = models.PositiveBigIntegerField(default=0, editable=False)
    verified_email = models.EmailField(blank=True, editable=False)
    email_verified_at = models.DateTimeField(null=True, blank=True, editable=False)
    email_verification_nonce = models.UUIDField(default=uuid.uuid4, editable=False)

    @property
    def is_email_verified(self):
        return bool(self.email_verified_at and self.verified_email == self.email)

    def _get_session_auth_hash(self, secret=None):
        # Version zero preserves existing Django sessions during this additive rollout.
        if self.session_version == 0:
            return super()._get_session_auth_hash(secret=secret)
        return salted_hmac(
            "accounts.User.session_version",
            f"{self.password}:{self.session_version}",
            secret=secret,
            algorithm="sha256",
        ).hexdigest()

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()

        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class AccountSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session = models.OneToOneField(
        "sessions.Session", on_delete=models.CASCADE, related_name="account_record"
    )
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField()
    device = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen", "-pk"]
        indexes = [models.Index(fields=["user", "-last_seen"], name="account_session_user_idx")]
