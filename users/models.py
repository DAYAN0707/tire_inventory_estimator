from django.db import models

class User(models.Model):
    staff_id = models.CharField("従業員ID",max_length=6,unique=True)
    staff_name = models.CharField("従業員名", max_length=50)
    password = models.CharField("パスワード", max_length=128) # DBに保存されるのは生パスワードではなくハッシュ化（100文字超）された値

    is_active = models.BooleanField("有効フラグ", default=True) # ユーザーが有効かどうかを示すフラグ（論理削除のため）
    is_staff = models.BooleanField("管理者権限", default=False) # 管理者かどうかを示すフラグ

    def __str__(self):
        return self.staff_name