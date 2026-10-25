import re
import unicodedata

import phonenumbers
import pycountry
from django.core.exceptions import ValidationError as DjangoValidationError
from localflavor.ar.forms import ARCUITField, ARDNIField, ARPostalCodeField
from rest_framework import serializers

from config.geography import ARGENTINE_PROVINCE_CODES, ARGENTINE_PROVINCES

from .models import Customer


def normalize_province(value: str) -> str:
    """Normaliza acentos, mayúsculas y espacios para comparar."""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(normalized.casefold().split())


PROVINCE_LOOKUP = {normalize_province(province): province for province in ARGENTINE_PROVINCES}

PROVINCE_LOOKUP["caba"] = "Ciudad Autónoma de Buenos Aires"
PROVINCE_LOOKUP["capital federal"] = "Ciudad Autónoma de Buenos Aires"


POSTAL_CODE_PATTERNS = {
    "US": r"\d{5}(?:-\d{4})?",
    "CA": r"[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ -]?\d[ABCEGHJ-NPRSTV-Z]\d",
    "GB": r"(?:GIR 0AA|[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})",
    "AU": r"\d{4}",
    "NZ": r"\d{4}",
    "DE": r"\d{5}",
    "FR": r"\d{5}",
    "ES": r"\d{5}",
    "IT": r"\d{5}",
    "NL": r"\d{4}\s?[A-Z]{2}",
    "BR": r"\d{5}-?\d{3}",
    "IN": r"\d{6}",
    "JP": r"\d{3}-?\d{4}",
    "MX": r"\d{5}",
    "CH": r"\d{4}",
    "AT": r"\d{4}",
    "BE": r"\d{4}",
    "PT": r"\d{4}-?\d{3}",
    "PL": r"\d{2}-?\d{3}",
    "SE": r"\d{3}\s?\d{2}",
    "NO": r"\d{4}",
    "DK": r"\d{4}",
    "FI": r"\d{5}",
    "ZA": r"\d{4}",
    "SG": r"\d{6}",
    "KR": r"\d{5}",
    "CN": r"\d{6}",
    "RU": r"\d{6}",
    "TR": r"\d{5}",
    "IL": r"\d{5,7}",
    "GR": r"\d{3}\s?\d{2}",
    "IE": r"[A-Z0-9]{3}\s?[A-Z0-9]{4}",
}


class CustomerSerializer(serializers.ModelSerializer):
    """
    Serializa clientes y valida sus datos.

    La empresa y el creador son de solo lectura:
    el servidor determina sus valores.
    """

    tenant = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "tenant",
            "customer_type",
            "name",
            "legal_name",
            "document_type",
            "document_number",
            "email",
            "phone",
            "address",
            "city",
            "province",
            "postal_code",
            "country_code",
            "notes",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        current = self.instance
        errors = {}

        def current_value(field, default=""):
            if field in attrs:
                return attrs[field]
            if current is not None:
                return getattr(current, field)
            return default

        def was_submitted(field):
            return current is None or field in attrs

        # Nombre principal.
        if was_submitted("name"):
            name = current_value("name")
            if not isinstance(name, str) or not name.strip():
                errors["name"] = "El nombre es obligatorio."
            else:
                attrs["name"] = name.strip()

        # País: validar contra el catálogo ISO.
        country_code = current_value("country_code", "AR")
        country_code = country_code.strip().upper() if isinstance(country_code, str) else ""

        country = (
            pycountry.countries.get(alpha_2=country_code)
            if re.fullmatch(r"[A-Z]{2}", country_code)
            else None
        )

        validate_country = was_submitted("country_code")
        if validate_country:
            if country is None:
                errors["country_code"] = "Seleccioná un país reconocido mediante su código ISO."
            else:
                attrs["country_code"] = country_code

        # Provincia/subdivisión coherente con el país.
        validate_province = current is None or "province" in attrs or "country_code" in attrs

        if validate_province:
            raw_province = current_value("province")
            province = raw_province.strip() if isinstance(raw_province, str) else ""

            if province and country is not None:
                canonical_province = None

                if country_code == "AR":
                    canonical_province = ARGENTINE_PROVINCE_CODES.get(
                        province.upper()
                    ) or PROVINCE_LOOKUP.get(normalize_province(province))
                else:
                    subdivisions = pycountry.subdivisions.get(country_code=country_code) or []

                    normalized_input = normalize_province(province)

                    for subdivision in subdivisions:
                        candidates = {
                            normalize_province(subdivision.name),
                            normalize_province(subdivision.code),
                            normalize_province(subdivision.code.split("-", 1)[-1]),
                        }

                        if normalized_input in candidates:
                            canonical_province = subdivision.name
                            break

                if canonical_province is None:
                    errors["province"] = (
                        "Seleccioná una provincia, estado o subdivisión "
                        "válida para el país elegido."
                    )
                else:
                    attrs["province"] = canonical_province

            elif not province:
                attrs["province"] = ""

        # Teléfono: analizar según las reglas internacionales.
        validate_phone = current is None or "phone" in attrs or "country_code" in attrs

        if validate_phone:
            phone = current_value("phone")
            phone = phone.strip() if isinstance(phone, str) else ""

            if not phone:
                attrs["phone"] = ""
            elif not re.fullmatch(r"\+?[0-9().\-\s]+", phone):
                errors["phone"] = "El teléfono contiene caracteres no permitidos."
            elif country is None:
                errors["phone"] = "Seleccioná un país válido para verificar el teléfono."
            else:
                try:
                    parsed_phone = phonenumbers.parse(
                        phone,
                        None if phone.startswith("+") else country_code,
                    )
                except phonenumbers.NumberParseException:
                    errors["phone"] = "No se pudo interpretar el número telefónico."
                else:
                    if not phonenumbers.is_valid_number(parsed_phone):
                        errors["phone"] = (
                            "El teléfono no coincide con un rango válido "
                            "de numeración para ese país."
                        )
                    else:
                        attrs["phone"] = phonenumbers.format_number(
                            parsed_phone,
                            phonenumbers.PhoneNumberFormat.E164,
                        )

        # Dirección: validar estructura, no afirmar que existe.
        if was_submitted("address"):
            address = current_value("address")
            address = address.strip() if isinstance(address, str) else ""

            if address and any(ord(char) < 32 or ord(char) == 127 for char in address):
                errors["address"] = "La dirección contiene caracteres de control no permitidos."
            elif address and not any(char.isalnum() for char in address):
                errors["address"] = "Ingresá una dirección con letras o números."
            else:
                attrs["address"] = address

        # Ciudad: limpiar espacios y rechazar caracteres de control.
        if was_submitted("city"):
            city = current_value("city")
            city = city.strip() if isinstance(city, str) else ""

            if city and any(ord(char) < 32 or ord(char) == 127 for char in city):
                errors["city"] = "La ciudad contiene caracteres no permitidos."
            else:
                attrs["city"] = city

        # Código postal: reglas por país.
        validate_postal = current is None or "postal_code" in attrs or "country_code" in attrs

        if validate_postal:
            postal = current_value("postal_code")
            postal = postal.strip().upper() if isinstance(postal, str) else ""

            if not postal:
                attrs["postal_code"] = ""
            elif country is None:
                errors["postal_code"] = "Primero seleccioná un país válido."
            elif country_code == "AR":
                normalized_postal = re.sub(r"[\s-]", "", postal)

                # Compatibilidad con registros existentes de cuatro dígitos.
                # Para CPA se utiliza el validador específico de Argentina.
                if re.fullmatch(r"\d{4}", normalized_postal):
                    attrs["postal_code"] = normalized_postal
                else:
                    try:
                        ARPostalCodeField().clean(normalized_postal)
                    except DjangoValidationError:
                        errors["postal_code"] = "Ingresá un código postal argentino válido."
                    else:
                        attrs["postal_code"] = normalized_postal
            else:
                pattern = POSTAL_CODE_PATTERNS.get(country_code)

                if pattern is not None:
                    normalized_postal = " ".join(postal.split())

                    if not re.fullmatch(pattern, normalized_postal):
                        errors["postal_code"] = (
                            "El código postal no coincide con el formato esperado para ese país."
                        )
                    else:
                        attrs["postal_code"] = normalized_postal
                elif not re.fullmatch(
                    r"[A-Z0-9][A-Z0-9 -]{0,10}[A-Z0-9]",
                    postal,
                ):
                    errors["postal_code"] = "Revisá el formato del código postal."
                else:
                    attrs["postal_code"] = postal

        # Documento: validar al crear o modificar sus campos.
        validate_document = (
            current is None or "document_type" in attrs or "document_number" in attrs
        )

        if validate_document:
            document_type = current_value("document_type")
            raw_number = current_value("document_number", None)
            document_number = raw_number.strip() if isinstance(raw_number, str) else raw_number

            if bool(document_type) != bool(document_number):
                errors["document_number"] = (
                    "Debés indicar el tipo y el número de documento juntos, o dejar ambos vacíos."
                )

            elif document_number:
                if document_type in {"dni", "cuit", "cuil"} and not re.fullmatch(
                    r"[0-9.\-\s]+", document_number
                ):
                    errors["document_number"] = (
                        "El documento solo admite dígitos y separadores habituales."
                    )
                    raise serializers.ValidationError(errors)
                normalized = (
                    "".join(char for char in document_number if char.isdigit())
                    if document_type
                    in {
                        Customer.DocumentType.CUIT,
                        Customer.DocumentType.CUIL,
                        Customer.DocumentType.DNI,
                    }
                    else document_number.upper()
                )

                if not normalized:
                    errors["document_number"] = "El número de documento no puede quedar vacío."
                else:
                    try:
                        if document_type == Customer.DocumentType.DNI:
                            ARDNIField().clean(normalized)
                        elif document_type in {
                            Customer.DocumentType.CUIT,
                            Customer.DocumentType.CUIL,
                        }:
                            ARCUITField().clean(normalized)
                    except DjangoValidationError:
                        errors["document_number"] = (
                            "El documento no tiene un formato o dígito verificador válido."
                        )
                    else:
                        attrs["document_number"] = normalized

                        request = self.context.get("request")
                        tenant = getattr(request, "tenant", None)

                        if tenant is not None:
                            duplicates = Customer.objects.filter(
                                tenant=tenant,
                                document_type=document_type,
                                document_number=normalized,
                            )

                            if current is not None:
                                duplicates = duplicates.exclude(pk=current.pk)

                            if duplicates.exists():
                                errors["document_number"] = (
                                    "Ya existe un cliente con ese documento en esta empresa."
                                )
            else:
                attrs["document_number"] = None

        if errors:
            raise serializers.ValidationError(errors)

        return attrs
