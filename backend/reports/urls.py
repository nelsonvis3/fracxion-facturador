from django.urls import path

from .views import ExportView

urlpatterns = [path("reports/export/", ExportView.as_view(), name="report-export")]
