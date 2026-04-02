from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

class EstimateItem(models.Model):
    # --- 既存のフィールド ---
    # 文字列 'アプリ名.モデル名' で指定することで読み込み順エラーを防ぐ
    estimate = models.ForeignKey('estimate.Estimate', related_name='items', on_delete=models.CASCADE) # 見積と見積アイテムは1対多の関係、見積が削除されたら関連するアイテムも削除
    tire = models.ForeignKey('inventory.Tire', on_delete=models.PROTECT, related_name="estimate_items", verbose_name='タイヤ') # 見積アイテムは特定のタイヤに紐づく、タイヤが削除されないよう PROTECT を指定
    quantity = models.IntegerField('購入本数', null=True, blank=True)
    unit_price = models.IntegerField('1本価格', blank=True, null=True) # 見積時の単価を保存（価格変更に影響されないため）
    set_price = models.IntegerField('4本特価', blank=True, null=True) # 見積時の4本特価を保存
    subtotal = models.IntegerField('タイヤ小計', blank=True, null=True) # 小計を保存（quantity × unit_price）
    
    work_quantity = models.IntegerField(
        '作業本数', 
        help_text="工賃・廃タイヤ・バルブの計算に使用します。スペアなど車体への取付(交換)作業が不要・持ち帰り分が含まれる場合は、数量を減らしてください。",
        default=4
    )

    # 工賃マスタと紐づけるための項目 (ここも文字列で指定)
    cost_master = models.ForeignKey('estimate.ChargeMaster', on_delete=models.PROTECT, null=True, blank=True, related_name="estimate_items")

    # --- 追加：計算ロジック（プロパティ） ---

    @property
    def calc_set_count(self):
        """4本セットの数を計算"""
        return (self.quantity or 0) // 4

    @property
    def calc_remainder(self):
        """セットにならなかった余りの本数を計算"""
        return (self.quantity or 0) % 4

    @property
    def has_set_price_applied(self):
        """
        4本特価が適用されているか判定。
        set_priceが0やNoneでないことを厳密にチェック
        """
        target_set_price = self.set_price if self.set_price is not None else self.tire.set_price
        return bool(target_set_price) and (self.quantity or 0) >= 4

    @property
    def calc_subtotal(self):
        """【重要】内訳ロジックと完全に一致させた小計計算"""
        u_price = self.unit_price if self.unit_price is not None else self.tire.unit_price
        s_price = self.set_price if self.set_price is not None else self.tire.set_price

        if self.has_set_price_applied:
            # (セット価格 × セット数) + (通常単価 × 余り)
            return (s_price * self.calc_set_count) + (u_price * self.calc_remainder)
        return u_price * (self.quantity or 0)

    @property
    def price_breakdown_list(self):
        """表示用の内訳リスト（HTMLテンプレートで使用）"""
        breakdown = []
        u_price = self.unit_price if self.unit_price is not None else self.tire.unit_price
        s_price = self.set_price if self.set_price is not None else self.tire.set_price

        if self.has_set_price_applied:
            if self.calc_set_count > 0:
                breakdown.append(f"4本特価：¥{s_price:,} × {self.calc_set_count}セット")
            if self.calc_remainder > 0:
                breakdown.append(f"通常価格：¥{u_price:,} × {self.calc_remainder}本")
        else:
            breakdown.append(f"通常価格：¥{u_price:,} × {self.quantity}本")
        return breakdown

    # --- 既存のメソッド ---

    def stock_judgement(self):
        # 見積本数 × 在庫数で在庫状態を判定
        tire = self.tire
        qty = self.quantity or 0

        # 在庫数が見積本数以上ある場合は「在庫有」と緑色で表示
        if tire.stock_qty >= qty:
            return "在庫有"

        # 発取り可能」とグレーで表示
        if tire.reorder_point == 0:
            return "取寄可能"

        # 発注点があり在庫数が定数以下の場合は「入荷待ち」と赤色で表示
        return "入荷待ち"

    # 見積時点の小計(単価×本数)を自動計算し、見積履歴としてDB保存
    def save(self, *args, **kwargs):  # 親クラスの save() メソッドをオーバーライド

        if self.estimate.is_fixed:
            raise ValidationError('確定済みの見積は編集できません')

        # 単価は常に1本価格
        self.unit_price = self.tire.unit_price
        # 4本特価もDBに保存（価格変更に影響されないため）
        self.set_price = self.tire.set_price

        # タイヤ代はあくまで「quantity（購入本数）」で計算
        # @property の計算結果を DBフィールドの subtotal に同期
        self.subtotal = self.calc_subtotal

        super().save(*args, **kwargs)

    # Item 削除時にも親 Estimate の見積合計を再計算
    def delete(self, *args, **kwargs):
        estimate = self.estimate  # 削除前に親 Estimate を取得
        super().delete(*args, **kwargs)
        estimate.recalc_total_price()  # 削除後に親 Estimate の合計を更新

    # 管理画面等での表示用
    def __str__(self):
        return f"{self.tire} x {self.quantity}本"