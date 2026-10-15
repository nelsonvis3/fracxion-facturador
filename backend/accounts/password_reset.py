import logging
from urllib.parse import urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.http import JsonResponse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from config.parsers import parse_json_body

from .rate_limits import is_rate_limited
from .security import security_event

logger = logging.getLogger(__name__)

User = get_user_model()

RESET_REQUEST_LIMIT = 5
RESET_CONFIRM_LIMIT = 10
RESET_RATE_WINDOW = 15 * 60


GENERIC_RESET_RESPONSE = {
    "detail": (
        "Si existe una cuenta activa con ese correo, "
        "recibirás instrucciones para restablecer tu contraseña."
    )
}


def _is_rate_limited(request, action, limit):
    """
    Limita intentos por IP usando la caché configurada en Django.

    No utiliza X-Forwarded-For: la IP se obtiene de REMOTE_ADDR
    para evitar confiar en cabeceras que el cliente pueda falsificar.
    """
    return is_rate_limited(request, action=f"reset-{action}", limit=limit)


@require_POST
@csrf_protect
@never_cache
def password_reset_request_view(request):
    """Solicita un enlace de recuperación por correo electrónico."""

    if _is_rate_limited(
        request,
        action="request",
        limit=RESET_REQUEST_LIMIT,
    ):
        response = JsonResponse(
            {"detail": ("Demasiadas solicitudes. Volvé a intentarlo más tarde.")},
            status=429,
        )
        response["Retry-After"] = str(RESET_RATE_WINDOW)
        return response

    payload = parse_json_body(request)

    if payload is None:
        return JsonResponse(
            {"detail": "Se esperaba un objeto JSON válido."},
            status=400,
        )

    email = payload.get("email")

    if not isinstance(email, str) or not email.strip() or len(email.strip()) > 254:
        return JsonResponse(
            {"detail": "Introducí un correo electrónico válido."},
            status=400,
        )

    # No diferenciamos la respuesta según exista la cuenta.
    response = JsonResponse(GENERIC_RESET_RESPONSE)
    security_event(request, event="password_reset_requested", outcome="accepted")

    # Evita bombardear una cuenta desde distintas direcciones IP.
    if is_rate_limited(
        request,
        action="reset-email",
        limit=RESET_REQUEST_LIMIT,
        identity=email.strip().lower(),
    ):
        return response

    users = User.objects.filter(
        email__iexact=email.strip(),
        is_active=True,
    )

    for user in users:
        if not user.has_usable_password():
            continue

        uid = urlsafe_base64_encode(force_bytes(user.pk))

        token = default_token_generator.make_token(user)

        query = urlencode(
            {
                "uid": uid,
                "token": token,
            }
        )

        frontend = urlsplit(settings.FRONTEND_PASSWORD_RESET_URL)
        reset_url = urlunsplit(
            (frontend.scheme, frontend.netloc, frontend.path, frontend.query, query)
        )

        subject = "Restablecer tu contraseña"
        message = (
            "Recibimos una solicitud para restablecer la "
            "contraseña de tu cuenta.\n\n"
            "Usá el siguiente enlace para elegir una contraseña nueva:\n\n"
            f"{reset_url}\n\n"
            "El enlace vence en una hora. Si no solicitaste "
            "este cambio, podés ignorar este mensaje.\n"
        )

        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception:
            # No revelamos errores de entrega al solicitante.
            # El formatter conserva tipo/ubicación, sin texto de excepción ni secretos.
            logger.exception(
                "No se pudo enviar el correo de recuperación.",
                extra={"request_id": getattr(request, "request_id", "")},
            )

    return response


@require_POST
@csrf_protect
@never_cache
def password_reset_confirm_view(request):
    """Valida el token y establece la nueva contraseña."""

    if _is_rate_limited(
        request,
        action="confirm",
        limit=RESET_CONFIRM_LIMIT,
    ):
        response = JsonResponse(
            {"detail": ("Demasiados intentos. Volvé a intentarlo más tarde.")},
            status=429,
        )
        response["Retry-After"] = str(RESET_RATE_WINDOW)
        return response

    payload = parse_json_body(request)

    if payload is None:
        return JsonResponse(
            {"detail": "Se esperaba un objeto JSON válido."},
            status=400,
        )

    uid = payload.get("uid")
    token = payload.get("token")
    password = payload.get("password")
    password_confirm = payload.get("password_confirm")

    if not all(
        isinstance(value, str) and value
        for value in (
            uid,
            token,
            password,
            password_confirm,
        )
    ):
        return JsonResponse(
            {"detail": "Los datos de recuperación están incompletos."},
            status=400,
        )

    if len(uid) > 64 or len(token) > 128 or len(password) > 4096 or len(password_confirm) > 4096:
        return JsonResponse(
            {"detail": "Los datos de recuperación exceden el tamaño permitido."}, status=400
        )

    if password != password_confirm:
        return JsonResponse(
            {"password_confirm": ["Las contraseñas no coinciden."]},
            status=400,
        )

    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User._default_manager.get(
            pk=user_id,
            is_active=True,
        )
    except (
        ValueError,
        TypeError,
        OverflowError,
        UnicodeDecodeError,
        User.DoesNotExist,
    ):
        return JsonResponse(
            {"detail": "El enlace no es válido o ha vencido."},
            status=400,
        )

    if not default_token_generator.check_token(user, token):
        return JsonResponse(
            {"detail": "El enlace no es válido o ha vencido."},
            status=400,
        )

    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        return JsonResponse(
            {"password": exc.messages},
            status=400,
        )

    # Volvemos a validar dentro de la transacción para evitar
    # que dos solicitudes concurrentes usen el mismo token.
    with transaction.atomic():
        locked_user = (
            User._default_manager.select_for_update()
            .filter(
                pk=user.pk,
                is_active=True,
            )
            .first()
        )

        if locked_user is None or not default_token_generator.check_token(
            locked_user,
            token,
        ):
            return JsonResponse(
                {"detail": "El enlace no es válido o ha vencido."},
                status=400,
            )

        try:
            validate_password(password, user=locked_user)
        except DjangoValidationError as exc:
            return JsonResponse(
                {"password": exc.messages},
                status=400,
            )

        locked_user.set_password(password)
        locked_user.save(update_fields=["password"])
        from django.contrib.sessions.models import Session

        Session.objects.filter(account_record__user=locked_user).delete()
        security_event(
            request, event="password_reset_completed", outcome="success", actor=locked_user
        )

    return JsonResponse(
        {
            "detail": (
                "La contraseña se restableció correctamente. Iniciá sesión con tu nueva contraseña."
            )
        }
    )
