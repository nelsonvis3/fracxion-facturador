from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from django.db import transaction

from . import mfa


class MFAAdminAuthenticationForm(AdminAuthenticationForm):
    otp_code = forms.CharField(
        label="Código MFA o de recuperación",
        required=False,
        max_length=64,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code"}),
    )

    def clean(self):
        data = super().clean()
        # Required-field validation may return without authenticating a user.
        if self.user_cache is None:
            return data
        with transaction.atomic():
            user = mfa.lock_user(self.user_cache.pk)
            if user is None or user.password != self.user_cache.password:
                raise ValidationError("Acceso inválido. Volvé a intentarlo.")
            device = mfa.lock_device(user)
            if device and device.confirmed_at:
                if not mfa.verify(device, data.get("otp_code", "").strip()):
                    raise ValidationError("Ingresá un código MFA válido que no hayas utilizado.")
                self.request._verified_mfa = (user.pk, str(device.generation))
        return data


def remember_admin_mfa(sender, request, user, **kwargs):
    verified = getattr(request, "_verified_mfa", None)
    if verified and verified[0] == user.pk:
        request.session[mfa.PROOF] = verified[1]
