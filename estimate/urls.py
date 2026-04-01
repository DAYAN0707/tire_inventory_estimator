from django.urls import path
from .views import estimate_views, api_views

app_name = 'estimate'

urlpatterns = [
    # --- 画面表示（HTML）系 ---
    path('', estimate_views.EstimateListView.as_view(), name='estimate_list'),
    path('create/', estimate_views.EstimateCreateView.as_view(), name='estimate_create'),
    path('<int:pk>/', estimate_views.EstimateDetailView.as_view(), name='estimate_detail'),

    # --- API（JSON）系 ---
    path('api/calculate-charges/', api_views.calculate_charges_api, name='calculate_charges_api'),
    path('<int:pk>/print/', estimate_views.estimate_print, name='estimate_print'),
]