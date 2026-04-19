from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from .models import AuditLog

class AuditLogListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """店長（管理者）専用の監査ログ一覧画面"""
    model = AuditLog
    template_name = 'audit/log_list.html'
    context_object_name = 'logs'
    ordering = ['-acted_at'] # 新しい順
    paginate_by = 20 # 1ページに表示する件数

    def test_func(self):
        """
        ログインユーザーが「スタッフ(is_staff)」または「管理者(is_superuser)」
        である場合のみ閲覧を許可する
        """
        return self.request.user.is_staff or self.request.user.is_superuser