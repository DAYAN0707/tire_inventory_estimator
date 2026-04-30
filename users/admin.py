from django.contrib import admin # Djangoの管理サイト機能を利用するためのインポート
from django.contrib.auth.admin import UserAdmin # Djangoの組み込みUserAdminをベースにカスタマイズするためのインポート
from .models import User # 同じフォルダのmodels.pyからUserモデルを読み込む

class CustomUserAdmin(UserAdmin):
    # 一覧画面に表示する項目
    list_display = ('staff_id', 'staff_name', 'username', 'is_staff', 'is_active')
    
    # 編集画面の設定
    fieldsets = UserAdmin.fieldsets + (
        ('追加情報', {'fields': ('staff_id', 'staff_name')}),
    )
    # 新規作成画面の設定
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('追加情報', {'fields': ('staff_id', 'staff_name')}),
    )

    # デモユーザー制限用のオーバーライド
    def has_add_permission(self, request):
        """新規作成（追加）を制限"""
        if request.user.groups.filter(name="demo_group").exists():
            return False
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        """編集を制限"""
        if request.user.groups.filter(name="demo_group").exists():
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        """削除を制限"""
        if request.user.groups.filter(name="demo_group").exists():
            return False
        return super().has_delete_permission(request, obj)

# 作成した設定を適用してUserモデルを登録
admin.site.register(User, CustomUserAdmin)