"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .health import health, ready
from .reference_views import country_list, country_subdivisions

urlpatterns = [
    path("health/", health, name="health"),
    path("ready/", ready, name="ready"),
    path("admin/", admin.site.urls),
    path("api/tenants/<uuid:tenant_id>/", include("tenancy.urls")),
    path("api/tenants/<uuid:tenant_id>/", include("analytics.urls")),
    path("api/tenants/<uuid:tenant_id>/", include("reports.urls")),
    path("api/tenants/<uuid:tenant_id>/", include("automation.urls")),
    path("api/tenants/<uuid:tenant_id>/", include("operations.urls")),
    path(
        "api/tenants/<uuid:tenant_id>/",
        include("customers.urls"),
    ),
    path(
        "api/tenants/<uuid:tenant_id>/",
        include("catalog.urls"),
    ),
    path(
        "api/tenants/<uuid:tenant_id>/",
        include("auditlog.urls"),
    ),
    path(
        "api/tenants/<uuid:tenant_id>/",
        include("billing.urls"),
    ),
    path(
        "api/auth/",
        include("accounts.urls"),
    ),
    path(
        "api/reference/countries/",
        country_list,
        name="reference-countries",
    ),
    path(
        "api/reference/countries/<str:country_code>/subdivisions/",
        country_subdivisions,
        name="reference-country-subdivisions",
    ),
]

# Keep the public demo's schema/debugging surface closed by default in production.
if not settings.PRODUCTION:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    ]
