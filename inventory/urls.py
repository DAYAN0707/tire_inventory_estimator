from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('tires/', views.tire_list, name='tire_list'),
    
    # 🎯今はまだ中身（View）がないので、とりあえず tire_list を指定
    path('order/<int:tire_id>/', views.tire_list, name='order_create'), 
]
