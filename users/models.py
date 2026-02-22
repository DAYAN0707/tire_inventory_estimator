from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    # Django の組み込み User モデルを拡張し、従業員IDと従業員名を追加(従業員IDと従業員名は必須項目)
    staff_id = models.CharField("従業員ID", max_length=6, unique=True)
    # 業務上は従業員IDの方が一意であれば十分なので従業員名は unique=False
    staff_name = models.CharField("従業員名", max_length=50)
    # Django の組み込み User モデルの is_active と is_staff を利用し、ユーザーの有効/無効と管理者権限を管理する方針
    is_active = models.BooleanField("有効フラグ", default=True)
    # Django の組み込み User モデルの is_staff を利用し、管理者権限を管理する方針(管理者はユーザー管理ができるが、一般ユーザーはユーザー管理不可)
    is_staff = models.BooleanField("管理者権限", default=False)

# 管理画面などでユーザーを識別しやすくする為、__str__ メソッドを従業員名に変更(従業員IDも表示したい場合は f"{self.staff_id} - {self.staff_name}" などに変更可能)
    def __str__(self):
        return self.staff_name or self.username
