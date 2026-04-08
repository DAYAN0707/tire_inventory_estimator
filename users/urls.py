from django.urls import path
from .views import StaffLoginView
from django.contrib.auth.views import LogoutView

app_name = 'users'

urlpatterns = [
    # http://127.0.0.1:8000/users/login/ で表示される設定
    path('login/', StaffLoginView.as_view(), name='login'),
    
    # ついでにログアウトも設定
    path('logout/', LogoutView.as_view(next_page='users:login'), name='logout'),
]