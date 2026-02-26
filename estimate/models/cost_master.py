from django.db import models

# 管理画面等での表示用
class CostMaster(models.Model):
    min_inch = models.PositiveIntegerField() # 最小インチ数
    max_inch = models.PositiveIntegerField() # 最大インチ数
    name = models.CharField(max_length=100)
    unit_price = models.IntegerField()
    price_per_tire = models.PositiveIntegerField() # タイヤ1本あたりの取付工賃（円単位）
    is_active = models.BooleanField(default=True) # 有効フラグ（無効にすると見積作成時の選択肢から外れる）

    # 管理画面で「（例）12-13インチ：1100円」と表示させ、設定ミスを防ぐ
    def __str__(self):
        return f"{self.min_inch}-{self.max_inch}インチ: {self.price_per_tire}円"