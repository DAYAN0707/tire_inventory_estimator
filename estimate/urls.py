from django.urls import path
from .views import estimate_views

app_name = 'estimate'

urlpatterns = [
    # 画面表示系
    path('create/', estimate_views.EstimateCreateView.as_view(), name='estimate_create'),
    path('<int:pk>/', estimate_views.EstimateDetailView.as_view(), name='estimate_detail'),
    # タイヤの単価・特価を返す
    path('api/get-tire-info/<int:tire_id>/', estimate_views.get_tire_info, name='get_tire_info'),
    # 諸費用をまとめて計算して返す
    path('api/calculate-charges/', estimate_views.calculate_charges_api, name='calculate_charges_api'),
]