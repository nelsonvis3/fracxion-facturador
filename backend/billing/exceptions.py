from rest_framework.exceptions import APIException


class IdempotencyConflict(APIException):
    status_code = 409
    default_code = "idempotency_conflict"
    default_detail = "Esta solicitud ya se procesó con otros datos. Revisá los cobros antes de volver a registrar."
