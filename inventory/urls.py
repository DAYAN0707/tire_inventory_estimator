from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('tires/', views.tire_list, name='tire_list'),
]