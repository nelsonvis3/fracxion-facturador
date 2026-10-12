import pycountry
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.schema import ReferenceListSerializer

from .geography import ARGENTINE_PROVINCE_CODES


@extend_schema(responses=ReferenceListSerializer)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def country_list(request):
    """Devuelve los países reconocidos por el catálogo ISO."""
    countries = sorted(
        pycountry.countries,
        key=lambda country: country.name.casefold(),
    )

    return Response(
        {
            "results": [
                {
                    "code": country.alpha_2,
                    "name": country.name,
                }
                for country in countries
            ]
        }
    )


@extend_schema(responses=ReferenceListSerializer)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def country_subdivisions(request, country_code):
    """Devuelve las subdivisiones registradas para un país ISO."""
    country_code = country_code.upper()
    country = pycountry.countries.get(alpha_2=country_code)

    if country is None:
        raise NotFound("El código de país no existe en el catálogo ISO.")

    if country_code == "AR":
        subdivisions = [
            {"code": code, "name": name} for code, name in ARGENTINE_PROVINCE_CODES.items()
        ]
    else:
        subdivisions = [
            {
                "code": subdivision.code,
                "name": subdivision.name,
            }
            for subdivision in (pycountry.subdivisions.get(country_code=country_code) or [])
        ]

    subdivisions.sort(key=lambda item: item["name"].casefold())

    return Response({"results": subdivisions})
