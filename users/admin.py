# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

# 管理画面で従業員IDと従業員名を見えるように設定
class CustomUserAdmin(UserAdmin):
    # 一覧画面に表示する項目
    list_display = ('staff_id', 'staff_name', 'username', 'is_staff', 'is_active')
    
    # 編集画面で項目をグループ化して表示
    fieldsets = UserAdmin.fieldsets + (
        ('追加情報', {'fields': ('staff_id', 'staff_name')}),
    )
    # 新規作成画面にも追加
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('追加情報', {'fields': ('staff_id', 'staff_name')}),
    )

# 作成した設定を適用してUserモデルを登録
admin.site.register(User, CustomUserAdmin)