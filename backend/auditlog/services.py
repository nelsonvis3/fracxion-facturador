from typing import Any

from .models import AuditEvent


def record_audit_event(
    *,
    action: str,
    entity_type: str,
    entity_id: str = "",
    tenant=None,
    actor=None,
    changes: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    request=None,
) -> AuditEvent:
    """
    Registra un evento de auditoría.

    Para operaciones de negocio, debe llamarse dentro de la misma
    transacción que modifica el registro auditado. Si falla el
    registro de auditoría, la operación de negocio debe revertirse
    junto con la transacción.

    No pasar contraseñas, tokens, cookies, secretos ni el cuerpo
    completo de una petición en changes o metadata.
    """

    if not isinstance(changes, (dict, type(None))):
        raise TypeError("changes debe ser un diccionario o None.")

    if not isinstance(metadata, (dict, type(None))):
        raise TypeError("metadata debe ser un diccionario o None.")

    # Completar el contexto desde la petición cuando corresponda.
    if request is not None:
        if tenant is None:
            tenant = getattr(request, "tenant", None)

        if actor is None:
            request_user = getattr(request, "user", None)

            if getattr(request_user, "is_authenticated", False):
                actor = request_user

    # No asociar usuarios anónimos al campo actor.
    if not getattr(actor, "is_authenticated", False):
        actor = None

    ip_address = None
    user_agent = ""
    request_id = ""

    if request is not None:
        # Usamos la IP observada por Django. No confiamos en
        # X-Forwarded-For hasta configurar proxies de confianza.
        ip_address = request.META.get("REMOTE_ADDR") or None

        user_agent = request.META.get(
            "HTTP_USER_AGENT",
            "",
        )[:512]

        # Este identificador es de correlación, no de autenticación.
        request_id = getattr(request, "request_id", "")[:100]

    return AuditEvent.objects.create(
        tenant=tenant,
        actor=actor,
        action=action,
        entity_type=entity_type[:100],
        entity_id=str(entity_id)[:100],
        changes=changes or {},
        metadata=metadata or {},
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
