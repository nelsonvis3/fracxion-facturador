import json
import logging
import sys
import uuid
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from auditlog.models import AuditEvent
from tenancy.models import Membership, Tenant

from .observability import SafeJSONFormatter


class ObservabilityTests(TestCase):
    def test_interpolation_and_exception_text_do_not_leak_secrets(self):
        try:
            raise RuntimeError("SYNTHETIC_SECRET_TOKEN_IN_ERROR")
        except RuntimeError:
            record = logging.LogRecord(
                "accounts.password_reset",
                logging.ERROR,
                __file__,
                15,
                "SMTP operation failed: %s",
                ("SYNTHETIC_SECRET_PASSWORD",),
                sys.exc_info(),
            )
        record.request_id = str(uuid.uuid4())
        output = SafeJSONFormatter().format(record)
        data = json.loads(output)
        self.assertEqual(data["exception_type"], "RuntimeError")
        self.assertTrue(data["frames"])
        self.assertIn("request_id", data)
        for secret in ["SYNTHETIC_SECRET_TOKEN_IN_ERROR", "SYNTHETIC_SECRET_PASSWORD"]:
            self.assertNotIn(secret, output)

    def test_invalid_correlation_extras_are_not_serialized(self):
        record = logging.LogRecord(
            "config", logging.INFO, __file__, 20, "synthetic_event", (), None
        )
        record.request_id = "injected\nforged header"
        record.job_id = {"secret": "never serialize this"}
        data = json.loads(SafeJSONFormatter().format(record))
        self.assertNotIn("request_id", data)
        self.assertNotIn("job_id", data)

    def test_server_generated_request_id_matches_transactional_audit(self):
        user = get_user_model().objects.create_user(email="traceability@example.com")
        tenant = Tenant.objects.create(name="Traceability", slug="traceability")
        Membership.objects.create(user=user, tenant=tenant, role="owner")
        client = APIClient()
        client.force_authenticate(user)
        forged = str(uuid.uuid4())
        response = client.post(
            f"/api/tenants/{tenant.pk}/customers/",
            {"name": "Synthetic traced customer"},
            format="json",
            HTTP_X_REQUEST_ID=forged,
        )
        self.assertEqual(response.status_code, 201)
        correlation = response["X-Request-ID"]
        uuid.UUID(correlation)
        self.assertNotEqual(correlation, forged)
        event = AuditEvent.objects.get(tenant=tenant, entity_type="customers.customer")
        self.assertEqual(event.request_id, correlation)

    def test_django_request_logs_include_only_valid_status_and_correlation(self):
        record = logging.LogRecord(
            "django.request",
            logging.WARNING,
            __file__,
            1,
            "%s: %s",
            ("private URL", "private query"),
            None,
        )
        correlation = str(uuid.uuid4())
        record.request = SimpleNamespace(request_id=correlation, body="SYNTHETIC_SECRET")
        record.status_code = 403
        output = SafeJSONFormatter().format(record)
        self.assertEqual(json.loads(output)["request_id"], correlation)
        self.assertEqual(json.loads(output)["status_code"], 403)
        self.assertNotIn("private", output)
        self.assertNotIn("SYNTHETIC_SECRET", output)
        record.status_code = "injected status"
        self.assertNotIn("status_code", json.loads(SafeJSONFormatter().format(record)))
