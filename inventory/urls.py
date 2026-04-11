from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('tires/', views.tire_list, name='tire_list'),
    path('order/<int:tire_id>/', views.order_create, name='order_create'),
    path('orders/', views.order_list, name='order_list'), # 🎯 発注一覧画面
    path('order/confirm/<int:order_id>/', views.order_confirm, name='order_confirm'), # 🎯 確定処理
    path('order/cancel/<int:order_id>/', views.order_cancel, name='order_cancel'), # 🎯 キャンセル処理
]
