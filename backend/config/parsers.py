"""Lectura JSON acotada para autenticación y recursos comerciales."""

from io import BytesIO
from math import isfinite

from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser
from rest_framework.utils import json

MAX_JSON_BYTES = 2_621_440
MAX_JSON_DEPTH = 100


def validate_json_value(data, *, validate_text=True):
    """Evita texto no almacenable, números no finitos y estructuras excesivas."""
    pending = [(data, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise ValueError("El JSON excede la profundidad permitida.")
        if isinstance(value, str) and validate_text:
            if "\x00" in value:
                raise ValueError("El JSON contiene texto inválido.")
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("El JSON contiene texto inválido.") from exc
        elif isinstance(value, float) and not isfinite(value):
            raise ValueError("El JSON contiene un número no finito.")
        elif isinstance(value, dict):
            pending.extend((key, depth + 1) for key in value)
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
    return data


def parse_json_body(request, *, validate_text=True):
    """Devuelve un objeto JSON válido o None, sin propagar errores de entrada."""
    if request.content_type != "application/json":
        return None
    try:
        body = request.body
        if len(body) > MAX_JSON_BYTES:
            return None
        data = validate_json_value(json.loads(body), validate_text=validate_text)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


class SafeJSONParser(JSONParser):
    """Mantiene el contrato DRF y rechaza entradas inválidas antes de los modelos."""

    def parse(self, stream, media_type=None, parser_context=None):
        body = stream.read(MAX_JSON_BYTES + 1)
        if len(body) > MAX_JSON_BYTES:
            raise ParseError("El JSON excede el tamaño permitido.")
        try:
            data = super().parse(BytesIO(body), media_type, parser_context)
            return validate_json_value(data)
        except (ValueError, RecursionError) as exc:
            raise ParseError("El JSON contiene datos inválidos.") from exc
