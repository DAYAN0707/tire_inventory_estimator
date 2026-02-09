from django.db import models
from .estimate import Estimate
from .tire import Tire

class EstimateItem(models.Model):
    estimate = models.ForeignKey(Estimate, on_delete=models.CASCADE, related_name='items')
    #過去見積があるタイヤは削除できない(履歴保全)
    tire = models.ForeignKey(Tire, on_delete=models.PROTECT,related_name='estimate_items')
    # default は設定しない（本数入力は必須とする）
    quantity = models.PositiveIntegerField('本数')
    #見積時単価を保存(価格変更に影響されないため)
    unit_price = models.DecimalField('見積時単価',max_digits=8,decimal_places=0)

# 見積時合計金額(単価×本数)、二重管理を防ぐ為、DBには保存しない
    @property
    def total_price(self):
        return self.unit_price * self.quantity
    
    def __str__(self):
        return f"{self.tire} x {self.quantity}本"
