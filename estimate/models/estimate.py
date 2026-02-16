from django.db import models

class Estimate(models.Model):
    # 
    created_by = models.ForeignKey('users.User',on_delete=models.PROTECT,verbose_name="見積作成者")
    estimate_number = models.CharField('見積番号', max_length=50, unique=True)
    customer_name = models.CharField('顧客名', max_length=100)
    # 見積の状態管理が目的の為、現時点では逆参照を使わずシンプルな ForeignKey
    status = models.ForeignKey('estimate.EstimateStatus', on_delete=models.PROTECT)
    is_fixed = models.BooleanField('確定フラグ', default=False)
    # 外税内税の切替・会計システム連携の際は IntegerField を DecimalField に変更検討
    total_price = models.IntegerField('見積時合計金額', default=0) #円単位・税込固定
    created_at = models.DateTimeField('作成日時', auto_now_add=True)

# ステータスに応じて見積を自動ロック（業務ルールをモデル層で担保）
    def save(self, *args, **kwargs):
        # 例えば、status が「契約済み」「キャンセル済み」などの場合
        if self.status:
            self.is_fixed = self.status.is_fixed # Status モデルの is_fixed フィールドを参照
        
        super().save(*args, **kwargs) # 親クラスの save() メソッドを呼び出して保存

    def __str__(self):
        return f"Estimate {self.estimate_number} for {self.customer_name}"

# 見積時合計金額を再計算して保存するメソッド
    def recalc_total_price(self):
        total = sum(item.subtotal for item in self.items.all())
        self.total_price = total
        self.save(update_fields=['total_price'])

        