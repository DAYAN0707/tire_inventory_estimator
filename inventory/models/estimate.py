from django.db import models

class Estimate(models.Model):
    estimate_number = models.CharField('見積番号', max_length=50, unique=True)
    customer_name = models.CharField('顧客名', max_length=100)
    # 外税内税の切替・会計システム連携の際はDecimalFieldに変更検討
    total_price = models.IntegerField('見積時合計金額',max_digits=10,decimal_places=0) #円単位・税込固定
    created_at = models.DateTimeField('作成日時', auto_now_add=True)

    def __str__(self):
        return f"Estimate {self.estimate_number} for {self.customer_name}"

# 見積時合計金額を再計算して保存するメソッド
    def recalc_total_price(self):
        total = sum(item.subtotal for item in self.items.all())
        self.total_price = total
        self.save(update_fields=['total_price'])