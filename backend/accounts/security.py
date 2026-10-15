"""Minimal platform security events: never store request bodies, email or tokens."""

from auditlog.models import AuditEvent
from auditlog.services import record_audit_event


def security_event(request, *, event, outcome, actor=None):
    action = {"login": AuditEvent.Action.LOGIN, "logout": AuditEvent.Action.LOGOUT}.get(
        event, AuditEvent.Action.SYSTEM
    )
    return record_audit_event(
        action=action,
        entity_type="accounts.security",
        actor=actor,
        entity_id=str(actor.pk) if actor else "",
        request=request,
        metadata={
            "event": event,
            "outcome": outcome,
            "channel": "admin" if request.path.startswith("/admin/") else "api",
        },
    )
