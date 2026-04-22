"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    # 🎯 サイト全体のTOP（http://127.0.0.1:8000/）にアクセスした時の動き
    # ログイン状況を判断してリダイレクト（※タイヤ一覧へ飛ばす設定）
    path('', RedirectView.as_view(url='/inventory/tires/'), name='index'),

    # --- 各アプリケーションのURL設定 ---
    
    # Django標準の管理画面（データベースの値を直接操作・確認できる場所）
    path('admin/', admin.site.urls),
    # ログイン・ログアウト関連（Django標準の認証機能を利用）
    path('accounts/', include('django.contrib.auth.urls')),
    # 見積管理アプリ（見積作成・詳細・ステータス更新など）
    path('estimate/', include('estimate.urls')),
    # タイヤ・在庫管理アプリ（タイヤ一覧・在庫数管理・発注処理など）
    path('inventory/', include('inventory.urls')),
    # ユーザー・従業員管理アプリ（従業員の追加・編集など）
    path('users/', include('users.urls')),
    # 監査ログ確認アプリ（いつ、誰が、何を操作したかの記録確認）
    path('audit/', include('audit.urls')),
]
