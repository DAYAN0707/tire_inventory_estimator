from django.db import models

class EstimateItem(models.Model):
    # ForeignKeyの相手を Estimate(クラス名)ではなく'アプリ名.モデル名'(文字列)で指定＝インポートを書かずに済む
    estimate = models.ForeignKey('estimate.Estimate', on_delete=models.CASCADE, related_name='items')
    # 過去見積があるタイヤは削除できない(履歴保全)
    tire = models.ForeignKey('inventory.Tire', on_delete=models.PROTECT, related_name='estimate_items')
    # default は設定しない（本数入力は必須とする）
    quantity = models.PositiveIntegerField('本数')
    # 見積時単価を保存(価格変更に影響されないため)
    unit_price = models.DecimalField('見積時単価',max_digits=8,decimal_places=0)
    # quantity * unit_price を保存時に固定する
    subtotal = models.IntegerField('小計', editable=False)

    # 見積時点の小計(単価×本数)を自動計算し、見積履歴としてDB保存
    def save(self, *args, **kwargs):  # 親クラスの save() メソッドをオーバーライド
        if self.estimate.is_fixed:
            raise ValueError('確定済みの見積は編集できません')
    
    # 見積が確定している場合、unit_priceをタイヤの現在価格に固定
        self.subtotal = self.unit_price * self.quantity
        super().save(*args, **kwargs)  # 親クラスの save() メソッドを呼び出して保存
        # Item が追加・変更される度、親 Estimate の見積合計を自動更新
        self.estimate.recalc_total_price()
    
    # Item 削除時にも親 Estimate の見積合計を再計算
    def delete(self, *args, **kwargs):
        estimate = self.estimate  # 削除前に親 Estimate を取得
        super().delete(*args, **kwargs)
        estimate.recalc_total_price()  # 削除後に親 Estimate の合計を更新

    # 管理画面等での表示用
    def __str__(self):
        return f"{self.tire} x {self.quantity}本"
