from django.urls import path
from .views import EstimateCreateView, EstimateDetailView

app_name = "estimate"

urlpatterns = [
    path("create/", EstimateCreateView.as_view(), name="estimate_create"),
    path("<int:pk>/", EstimateDetailView.as_view(), name="estimate_detail"),
]