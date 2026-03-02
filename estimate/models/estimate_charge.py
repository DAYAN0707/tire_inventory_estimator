from django.db import models
from .cost_master import CostMaster

# 見積に紐づく諸費用を管理するモデル
class EstimateCharge(models.Model):
    estimate = models.ForeignKey(
        'Estimate',
        related_name='charges', #見積から諸費用を逆参照するための related_name を追加
        on_delete=models.CASCADE, #見積が削除されたら関連する諸費用も削除
        verbose_name='見積'
    )
    # 諸費用の種類を管理する外部キー（例: 取付工賃、廃タイヤ、エアバルブなど）
    cost_master = models.ForeignKey(
        CostMaster, # 諸費用のマスタモデルへの外部キー
        on_delete=models.PROTECT, # 諸費用のマスタが削除されないように PROTECT を指定
        verbose_name='諸費用'
    )

    quantity = models.IntegerField('作業本数', default=0) # 取付工賃などで本数連動する場合の本数を管理するフィールド（例: 4本分の取付工賃なら quantity=4、エアバルブ交換で3本必要なら quantity=3 など）
    unit_price = models.IntegerField('単価') # 見積時の単価を保存（価格変更に影響されないため）
    subtotal = models.IntegerField('小計') # 小計を保存（quantity × unit_price）

    # 重要：これが無いと「どのタイヤの工賃か」分からない！！！
    item = models.ForeignKey("EstimateItem",on_delete=models.CASCADE,null=True,blank=True)

    # 管理画面等での表示用
    def save(self, *args, **kwargs):
        # 整数の商：4本セットがいくつ取れるか (例: 6本なら 1セット)
        num_sets = self.quantity // 4

        # 剰余：セットにならなかった余りは何本か (例: 6本なら 2本)
        remainder = self.quantity % 4

        # 合計金額を計算　(セット数 × 4本特価) + (余り本数 × 1本単価)
        self.subtotal = (num_sets * self.set_price) + (remainder * self.unit_price)

        super().save(*args, **kwargs)


    def remove_option_fees(self):
        # 諸費用マスタ(cost_master)のカテゴリー(category)が 'option' のものを消す、という書き方
        self.charges.filter(cost_master__category='option').delete()