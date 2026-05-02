from django.urls import path # URLパターンを定義するための関数をインポート
from .views import estimate_views, api_views # views.py内のestimate_viewsとapi_viewsをインポート
from django.contrib.auth.views import LogoutView # ログアウト処理を行うための組み込みビューをインポート
from django.contrib import admin # 管理サイトのURLを定義するためにadminをインポート

# アプリケーション名を定義（URLの逆引きに使用）
app_name = 'estimate'

urlpatterns = [
    # --- 画面表示（HTML）系 ---
    # 見積の一覧画面と新規作成画面へのURLを定義
    path('', estimate_views.EstimateListView.as_view(), name='estimate_list'),
    # 新規見積作成画面へのURLを定義
    path('create/', estimate_views.EstimateCreateView.as_view(), name='estimate_create'),
    
    # 既存の 'estimate_detail' はそのまま
    # 見積の詳細画面へのURLを定義
    path('<int:pk>/', estimate_views.EstimateDetailView.as_view(), name='estimate_detail'),

    # --- 見積追加ロジック ---
    # estimate_views内の add_item 関数を呼び出す設定
    path('add-item/<int:tire_id>/', estimate_views.add_item, name='add_item'),

    # --- API（JSON）系 / その他 ---
    # APIエンドポイントのURLを定義（例: 諸費用の計算API）
    path('api/calculate-charges/', api_views.calculate_charges_api, name='calculate_charges_api'),
    # 見積の印刷用URL（PDF出力など）を定義
    path('<int:pk>/print/', estimate_views.estimate_print, name='estimate_print'),


    # --- 店長権限専用の在庫管理画面URL ---
    # 店長が見積作成の途中で在庫確認に来た場合、元の見積画面に戻れるようIDを取得してURLに含める
    path('manager/tires/', estimate_views.ManagerTireListView.as_view(), name='manager_tire_list'),
    # 店長用のタイヤ編集URL（例: タイヤの6桁コードや価格を変更するための画面）
    path('manager/tires/<int:pk>/edit/', estimate_views.ManagerTireUpdateView.as_view(), name='manager_tire_edit'),

    # --- 店長用：諸費用（工賃・廃タイヤ等）マスタ管理 ---
    # 諸費用マスタの一覧・編集・新規作成URLを定義
    path('manager/charges/', estimate_views.ManagerChargeListView.as_view(), name='manager_charge_list'),
    # 諸費用の新規作成URL
    path('manager/charges/add/', estimate_views.ManagerChargeCreateView.as_view(), name='manager_charge_add'),
    # 諸費用の編集URL（例: 工賃の金額を変更する等）
    path('manager/charges/<int:pk>/edit/', estimate_views.ManagerChargeUpdateView.as_view(), name='manager_charge_edit'),
    # 諸費用の有効化URL（例: 工賃を見積に反映させるためのスイッチ）
    path('manager/charges/<int:pk>/activate/', estimate_views.charge_master_activate, name='manager_charge_activate'),

    # --- 店長用：ステータスマスタ管理 ---
    # ステータスマスタの一覧・編集・新規作成URLを定義
    path('manager/statuses/', estimate_views.ManagerStatusListView.as_view(), name='status_list'),
    # ステータスの編集URL（例: 予約確定、キャンセル等のステータスを管理）
    path('manager/statuses/<int:pk>/edit/', estimate_views.ManagerStatusUpdateView.as_view(), name='status_edit'),
    # ステータスの新規作成URL
    path('manager/statuses/create/', estimate_views.ManagerStatusCreateView.as_view(), name='status_create'),

    # --- その他管理機能 ---
    # 店長用：見積のドラフト一括削除URL
    path('manager/clean-drafts/', estimate_views.clean_draft_estimates, name='clean_drafts'),
    # 店長用：ダッシュボードURL
    path('manager/dashboard/', estimate_views.ManagerDashboardView.as_view(), name='manager_dashboard'),
    # 見積のステータス更新URL（例: 予約確定、キャンセル等）
    path('<int:pk>/update-status/', estimate_views.EstimateStatusUpdateView.as_view(), name='update_status'),
    # 見積のPDF出力URL（例: 印刷用のPDFを生成するためのURL）
    path('logout/', LogoutView.as_view(next_page='users:login'), name='logout'),
    # Django標準の管理画面（データベースの値を直接操作・確認できる場所）へのURLを定義
    path('admin/', admin.site.urls),
]