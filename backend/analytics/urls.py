from django.urls import path

from .views import OverviewView, RecordCountsView

urlpatterns = [
    path("analytics/overview/", OverviewView.as_view(), name="analytics-overview"),
    path("analytics/records/", RecordCountsView.as_view(), name="record-counts"),
]
