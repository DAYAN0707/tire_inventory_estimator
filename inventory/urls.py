from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # 🎯 お客さんと一緒に見る「カード型」一覧画面
    path('tires/', views.tire_list, name='tire_list'),
    # 🎯 店員専用の「リスト型」在庫管理画面
    path('admin/tires/', views.tire_list_admin, name='tire_list_admin'),
    # 🎯 発注一覧画面
    path('orders/', views.order_list, name='order_list'),
    # 🎯 発注関連のURL
    path('order/<int:tire_id>/', views.order_create, name='order_create'),
    # 🎯 発注確定・キャンセルのURL（仮作成したOrderを操作する）
    path('order/confirm/<int:order_id>/', views.order_confirm, name='order_confirm'),
    # 🎯 発注キャンセルのURL
    path('order/cancel/<int:order_id>/', views.order_cancel, name='order_cancel'),

    # --- 🛠️ 店長権限：タイヤブランド管理 ---
    # 🎯 ブランド一覧画面（パスを 'list/' に変更して、他のURLと完全に区別）
    path('manager/brands/list/', views.BrandListView.as_view(), name='brand_list'),
    # 🎯 新規ブランド登録画面
    path('manager/brands/create/', views.BrandCreateView.as_view(), name='brand_create'),
    # 🎯 ブランドの編集・削除画面
    path('manager/brands/<int:pk>/edit/', views.BrandUpdateView.as_view(), name='brand_edit'),
]