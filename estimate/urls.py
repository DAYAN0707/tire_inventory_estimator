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

    # --- 店長権限専用の在庫管理画面URL  ---
    path('manager/tires/', estimate_views.ManagerTireListView.as_view(), name='manager_tire_list'),
    path('manager/tires/<int:pk>/edit/', estimate_views.ManagerTireUpdateView.as_view(), name='manager_tire_edit'),
    path('manager/charges/', estimate_views.ManagerChargeListView.as_view(), name='manager_charge_list'),
    path('manager/charges/add/', estimate_views.ManagerChargeCreateView.as_view(), name='manager_charge_add'),
    path('manager/charges/<int:pk>/edit/', estimate_views.ManagerChargeUpdateView.as_view(), name='manager_charge_edit'),
    # --- 店長用：ステータスマスタ管理 ---
    path('manager/statuses/', estimate_views.ManagerStatusListView.as_view(), name='status_list'),
    path('manager/statuses/<int:pk>/edit/', estimate_views.ManagerStatusUpdateView.as_view(), name='status_edit'),
    path('manager/statuses/create/', estimate_views.ManagerStatusCreateView.as_view(), name='status_create'),
    path('manager/clean-drafts/', estimate_views.clean_draft_estimates, name='clean_drafts'),
    # --- 店長・一般スタッフ共通：ポータル画面 ---
    path('manager/dashboard/', estimate_views.ManagerDashboardView.as_view(), name='manager_dashboard'),
]
