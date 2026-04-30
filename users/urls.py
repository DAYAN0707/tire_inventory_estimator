from django.urls import path # URLパターンを定義するための関数をインポート
from django.contrib.auth.views import LogoutView # ログアウト処理を行うための組み込みビューをインポート
from . import views  # views.pyから一括インポート

app_name = 'users'

urlpatterns = [
    # --- 認証系 ---
    # ログイン
    path('login/', views.StaffLoginView.as_view(), name='login'),
    # ログアウト
    path('logout/', LogoutView.as_view(next_page='users:login'), name='logout'),

    # --- ユーザー管理系（店長権限画面） ---
    # 一覧画面
    path('manager/list/', views.UserListView.as_view(), name='user_list'),
    # 新規登録
    path('manager/create/', views.UserCreateView.as_view(), name='user_create'),
    # 編集・削除
    path('manager/<int:pk>/edit/', views.UserUpdateView.as_view(), name='user_edit'),
]