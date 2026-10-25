"""Transactional email over HTTPS for hosts that block SMTP ports."""

import json
from email.utils import parseaddr
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend


class EmailDeliveryError(Exception):
    """Safe to log: never contains recipient addresses, tokens or provider bodies."""


def mailbox(value):
    name, address = parseaddr(value)
    if not address or "@" not in address or "\n" in value or "\r" in value:
        raise EmailDeliveryError("Dirección de correo inválida.")
    return {"email": address, **({"name": name} if name else {})}


class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not settings.BREVO_API_KEY:
            raise ImproperlyConfigured("Configurá BREVO_API_KEY.")
        sent = 0
        for message in email_messages or []:
            if not message.recipients():
                continue
            try:
                # Validate Django's header rules before translating to the API.
                message.message()
                if message.attachments or message.extra_headers or len(message.reply_to) > 1:
                    raise EmailDeliveryError("Formato de correo no soportado por este transporte.")
                payload = {
                    "sender": mailbox(message.from_email),
                    "subject": message.subject,
                    "htmlContent"
                    if message.content_subtype == "html"
                    else "textContent": message.body,
                }
                for field in ("to", "cc", "bcc"):
                    if addresses := getattr(message, field):
                        payload[field] = [mailbox(value) for value in addresses]
                if message.reply_to:
                    payload["replyTo"] = mailbox(message.reply_to[0])
                for content, mimetype in getattr(message, "alternatives", []):
                    if mimetype != "text/html":
                        raise EmailDeliveryError("Alternativa de correo no soportada.")
                    payload["htmlContent"] = content
                request = Request(
                    "https://api.brevo.com/v3/smtp/email",
                    data=json.dumps(payload).encode(),
                    headers={
                        "api-key": settings.BREVO_API_KEY,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    method="POST",
                )
                try:
                    with urlopen(request, timeout=settings.EMAIL_TIMEOUT) as response:
                        if response.status != 201:
                            raise EmailDeliveryError("El proveedor no aceptó el correo.")
                except HTTPError as exc:
                    code = exc.code
                    exc.close()
                    raise EmailDeliveryError(
                        f"El proveedor rechazó el correo (HTTP {code})."
                    ) from None
                except (URLError, OSError):
                    raise EmailDeliveryError(
                        "No se pudo conectar con el proveedor de correo."
                    ) from None
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent
