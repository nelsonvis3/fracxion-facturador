"""Transactional email over HTTPS for hosts that block SMTP ports."""

import json
from email.utils import formataddr, parseaddr
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


class HTTPSEmailBackend(BaseEmailBackend):
    """Shared validation and error handling; subclasses only describe the provider API."""

    key_setting = ""
    endpoint = ""
    accepted_status = 200

    def headers(self, key):
        raise NotImplementedError

    def payload(self, message, html):
        raise NotImplementedError

    def accepted(self, response):
        return response.status == self.accepted_status

    def send_messages(self, email_messages):
        key = getattr(settings, self.key_setting, "")
        if not key:
            raise ImproperlyConfigured(f"Configurá {self.key_setting}.")
        sent = 0
        for message in email_messages or []:
            if not message.recipients():
                continue
            try:
                # Validate Django's header rules before translating to the API.
                message.message()
                if message.attachments or message.extra_headers or len(message.reply_to) > 1:
                    raise EmailDeliveryError("Formato de correo no soportado por este transporte.")
                html = message.body if message.content_subtype == "html" else None
                for content, mimetype in getattr(message, "alternatives", []):
                    if mimetype != "text/html":
                        raise EmailDeliveryError("Alternativa de correo no soportada.")
                    html = content
                request = Request(
                    self.endpoint,
                    data=json.dumps(self.payload(message, html)).encode(),
                    headers={
                        **self.headers(key),
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "User-Agent": "Fracxion/1.0",
                    },
                    method="POST",
                )
                try:
                    with urlopen(request, timeout=settings.EMAIL_TIMEOUT) as response:
                        if not self.accepted(response):
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


class BrevoEmailBackend(HTTPSEmailBackend):
    key_setting = "BREVO_API_KEY"
    endpoint = "https://api.brevo.com/v3/smtp/email"
    accepted_status = 201

    def headers(self, key):
        return {"api-key": key}

    def payload(self, message, html):
        payload = {"sender": mailbox(message.from_email), "subject": message.subject}
        if message.content_subtype != "html":
            payload["textContent"] = message.body
        if html is not None:
            payload["htmlContent"] = html
        for field in ("to", "cc", "bcc"):
            if addresses := getattr(message, field):
                payload[field] = [mailbox(value) for value in addresses]
        if message.reply_to:
            payload["replyTo"] = mailbox(message.reply_to[0])
        return payload


def resend_address(value):
    box = mailbox(value)
    return formataddr((box.get("name", ""), box["email"]))


class ResendEmailBackend(HTTPSEmailBackend):
    key_setting = "RESEND_API_KEY"
    endpoint = "https://api.resend.com/emails"

    def headers(self, key):
        return {"Authorization": f"Bearer {key}"}

    def payload(self, message, html):
        payload = {"from": resend_address(message.from_email), "subject": message.subject}
        if message.content_subtype != "html":
            payload["text"] = message.body
        if html is not None:
            payload["html"] = html
        for field in ("to", "cc", "bcc"):
            if addresses := getattr(message, field):
                payload[field] = [resend_address(value) for value in addresses]
        if message.reply_to:
            payload["reply_to"] = resend_address(message.reply_to[0])
        return payload


def maileroo_address(value):
    box = mailbox(value)
    return {"address": box["email"], **({"display_name": box["name"]} if "name" in box else {})}


class MailerooEmailBackend(HTTPSEmailBackend):
    """Maileroo accepts free domains such as dpdns.org, which Resend rejects."""

    key_setting = "MAILEROO_API_KEY"
    endpoint = "https://smtp.maileroo.com/api/v2/emails"

    def headers(self, key):
        return {"Authorization": f"Bearer {key}"}

    def payload(self, message, html):
        payload = {"from": maileroo_address(message.from_email), "subject": message.subject}
        # An empty plain stops Maileroo from inventing a text part for HTML-only mail.
        payload["plain"] = message.body if message.content_subtype != "html" else ""
        if html is not None:
            payload["html"] = html
        for field in ("to", "cc", "bcc"):
            if addresses := getattr(message, field):
                payload[field] = [maileroo_address(value) for value in addresses]
        if message.reply_to:
            payload["reply_to"] = maileroo_address(message.reply_to[0])
        return payload


class AppsScriptEmailBackend(HTTPSEmailBackend):
    """Sends through a Google Apps Script web app so mail leaves from a Gmail account.

    Gmail rejects free domains like dpdns.org as spam; Gmail-to-Gmail is delivered.
    shortcut: consumer Gmail allows ~100 recipients/day, move to a paid domain if that is hit.
    """

    key_setting = "APPS_SCRIPT_MAIL_SECRET"

    @property
    def endpoint(self):
        url = settings.APPS_SCRIPT_MAIL_URL
        # The secret travels in the body, so never post it anywhere but Apps Script.
        if not url.startswith("https://script.google.com/macros/s/"):
            raise ImproperlyConfigured("Configurá APPS_SCRIPT_MAIL_URL.")
        return url

    def headers(self, key):
        return {}

    def payload(self, message, html):
        name = mailbox(message.from_email).get("name", "")
        payload = {
            "secret": settings.APPS_SCRIPT_MAIL_SECRET,
            "to": ",".join(mailbox(value)["email"] for value in message.to),
            "subject": message.subject,
            "body": message.body if message.content_subtype != "html" else "",
            "name": name,
        }
        if html is not None:
            payload["htmlBody"] = html
        for field in ("cc", "bcc"):
            if addresses := getattr(message, field):
                payload[field] = ",".join(mailbox(value)["email"] for value in addresses)
        if message.reply_to:
            payload["replyTo"] = mailbox(message.reply_to[0])["email"]
        return payload

    def accepted(self, response):
        # Apps Script answers 200 with an HTML error page when the script throws.
        try:
            return response.status == 200 and json.loads(response.read()).get("ok") is True
        except (ValueError, AttributeError):
            return False
