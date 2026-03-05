from django.urls import path
from . import views

app_name = "estimate"

urlpatterns = [
    path('create/', views.EstimateCreateView.as_view(), name='estimate_create'),
    ]