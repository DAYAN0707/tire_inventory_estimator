
from django.views.generic import ListView # クラスベースビューをインポート
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin # ログイン必須と権限チェックのためのミックスイン
from .models import AuditLog # 監査ログモデルをインポート
from django.contrib import messages # ユーザーへのフィードバック表示のためのインポート
from django.shortcuts import redirect # 画面表示、オブジェクト取得、リダイレクトのためのショートカット関数
from estimate.utils import is_manager, is_demo_staff_only # 役割判定のユーティリティ関数をインポート

class AuditLogListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """店長（管理者）専用の監査ログ一覧画面"""
    model = AuditLog
    template_name = 'audit/log_list.html'
    context_object_name = 'logs'
    ordering = ['-acted_at']
    paginate_by = 20

    def test_func(self):
        """UserPassesTestMixin の判定条件"""
        user = self.request.user
        # 判定1: まずは店長（is_staff）かどうか
        if not is_manager(user):
            return False
            
        # 判定2: デモスタッフ（店長権限なし）なら拒否
        # ここで False を返せば、下の handle_no_permission が即座に実行されます
        if is_demo_staff_only(user):
            return False
            
        return True

    def dispatch(self, request, *args, **kwargs):
        """リクエストが届いた直後の判定"""
        # test_func 側で強力に制限をかけるため、ここでの個別リダイレクトは不要になります。
        # 判定を test_func に一本化することで、すり抜けを防止します。
        return super().dispatch(request, *args, **kwargs)

    def handle_no_permission(self):
        """test_func が False を返した（権限がない）場合の挙動"""
        # ログイン画面に戻りつつ、赤い警告メッセージを表示
        # extra_tags='danger' を追加して Bootstrap の alert-danger（赤色）を適用
        messages.error(self.request, "監査ログの閲覧には店長権限が必要です。", extra_tags='danger')
        return redirect('users:login')