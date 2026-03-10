from django.db import models
from .estimate import Estimate
from .estimate_item import EstimateItem
from .masters.charge_master import ChargeMaster


# 見積時点での諸費用（工賃・オプション等）の確定情報を保存
class EstimateCharge(models.Model):

    """
    【設計の重要ポイント：マスタからのデカップリング】
    このモデルには計算ロジック（save()での自動計算など）を持たせない
    作成時に Calculator サービスが計算した「その瞬間の単価・小計」をそのまま保存
    将来マスタ価格が改定されても過去の見積金額が勝手に変わることを防ぐ！！
    """

    estimate = models.ForeignKey(
        Estimate,
        related_name='charges',
        on_delete=models.CASCADE,
        verbose_name='見積'
    )

    charge_master = models.ForeignKey(
        ChargeMaster,
        on_delete=models.PROTECT, # マスタが消されても、過去の見積データが消えないよう保護
        verbose_name='諸費用マスタ'
    )

    # 数量・単価・小計はすべて「数値」として直接保存（マスタへの依存を断ち切る）
    quantity = models.IntegerField(
        '作業本数', 
        default=0,
        help_text='取付工賃の本数や、廃タイヤの個数、エアバルブの個数など'
    )
    
    unit_price = models.IntegerField(
        '単価',
        help_text='見積作成時点のマスタ単価（RFT加算等を含む最終単価）'
    )
    
    subtotal = models.IntegerField(
        '小計',
        help_text='Calculatorによって計算済みの合計金額（単価×数量、または4本特価適用後）'
    )

    # どのタイヤに対する費用かを特定するための紐付け
    # ※前後サイズ違いの場合、どのタイヤの工賃かを判別するために必須
    item = models.ForeignKey(
        EstimateItem,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='対象タイヤ明細'
    )

    # プロのフラグ：システムが自動で作ったものか、人間が手で入れたものかを区別
    is_auto_generated = models.BooleanField('自動生成フラグ', default=True)

    # これが True の間は、自動計算ロジックはこの行の数量を勝手に変えません。
    is_manual_edited = models.BooleanField(
        '手動編集済み', 
        default=False, 
        help_text='数量を手動で変更した場合、自動計算の対象外になります'
    )

    def save(self, *args, **kwargs):
        # 単価 × 数量を常に計算
        self.subtotal = self.unit_price * self.quantity
        super().save(*args, **kwargs)


    class Meta:
        verbose_name = "見積諸費用"
        verbose_name_plural = "見積諸費用"

    def __str__(self):
        # 管理画面で「どの作業が何本分か」をひと目で確認できるようにする
        return f"{self.charge_master.name} × {self.quantity}本"


    """
    【削除処理の集約】
    かつてここにあった remove_option_fees() などの削除ロジックは、
    業務ルールの変更（例：キャンペーン中は消さない等）に対応しやすくする為、
    全て services/calculator.py 側に集約
    """