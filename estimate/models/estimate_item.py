from django.db import models
from django.conf import settings
from estimate.models.estimate import Estimate
from inventory.models import Tire
from django.core.exceptions import ValidationError


    # 管理画面で見積の状態を色分けして表示するためのプロパティ
class EstimateItem(models.Model):
    estimate = models.ForeignKey(Estimate, related_name='items', on_delete=models.CASCADE) # 見積と見積アイテムは1対多の関係、見積が削除されたら関連するアイテムも削除
    tire = models.ForeignKey(Tire, on_delete=models.PROTECT, related_name="estimate_items") # 見積アイテムは特定のタイヤに紐づく、タイヤが削除されないよう PROTECT を指定
    quantity = models.IntegerField() # 本数
    unit_price = models.IntegerField() # 見積時の単価を保存（価格変更に影響されないため）
    subtotal = models.IntegerField() # 小計を保存（quantity × unit_price）

    def stock_judgement(self):
        # 見積本数 × 在庫数で在庫状態を判定
        tire = self.tire
        qty = self.quantity

        # 在庫数が見積本数以上ある場合は「在庫有」と緑色で表示
        if tire.stock_qty >= qty:
            return "在庫有"

        # 発注点がない場合は「取寄可能」とグレーで表示
        if tire.reorder_point == 0:
            return "取寄可能"

        # 発注点があり在庫数が定数以下の場合は「入荷待ち」と赤色で表示
        return "入荷待ち"
    

    # 見積時点の小計(単価×本数)を自動計算し、見積履歴としてDB保存
    def save(self, *args, **kwargs):  # 親クラスの save() メソッドをオーバーライド
        if self.estimate.is_fixed:
            raise ValidationError('確定済みの見積は編集できません')
    
        if self.quantity >= 4 and self.tire.set_price:
            self.unit_price = self.tire.set_price // 4
        else:
            self.unit_price = self.tire.unit_price

    # 見積が確定している場合、unit_priceをタイヤの現在価格に固定
        self.subtotal = self.unit_price * self.quantity
        super().save(*args, **kwargs)  # 親クラスの save() メソッドを呼び出して保存
        # 見積確定前なら見積の合計金額を再計算して保存（見積アイテムの変更が見積全体の金額に反映されるようにするため）
        if not self.estimate.is_fixed:
            self.estimate.recalc_total_price()
    
    # Item 削除時にも親 Estimate の見積合計を再計算
    def delete(self, *args, **kwargs):
        estimate = self.estimate  # 削除前に親 Estimate を取得
        super().delete(*args, **kwargs)
        estimate.recalc_total_price()  # 削除後に親 Estimate の合計を更新

    # 管理画面等での表示用
    def __str__(self):
        return f"{self.tire} x {self.quantity}本"
