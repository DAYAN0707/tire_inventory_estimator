from django.urls import path
from .views import estimate_views, api_views

app_name = 'estimate'

urlpatterns = [
    # --- 画面表示（HTML）系 ---
    path('', estimate_views.EstimateListView.as_view(), name='estimate_list'),
    path('create/', estimate_views.EstimateCreateView.as_view(), name='estimate_create'),
    
    # 既存の 'estimate_detail' はそのまま
    path('<int:pk>/', estimate_views.EstimateDetailView.as_view(), name='estimate_detail'),

    # --- 見積追加ロジック ---
    # estimate_views内の add_item 関数を呼び出す設定
    path('add-item/<int:tire_id>/', estimate_views.add_item, name='add_item'),
    # 見積からのアイテム削除URL
    path('detail/<int:pk>/update-status/', estimate_views.update_status, name='update_status'),

    # --- API（JSON）系 / その他 ---
    path('api/calculate-charges/', api_views.calculate_charges_api, name='calculate_charges_api'),
    path('<int:pk>/print/', estimate_views.estimate_print, name='estimate_print'),
]