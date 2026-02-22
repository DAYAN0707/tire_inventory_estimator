from django.db import models
from django.conf import settings
from estimate.models.estimate_status import EstimateStatus

# 見積の基本情報を管理するモデル
class Estimate(models.Model):
    estimate_status = models.ForeignKey(EstimateStatus, on_delete=models.PROTECT, related_name='estimates') # 見積の状態を管理する外部キー(例: 作成中、契約済み、キャンセル済みなど)
    # デフォルトは「作成中」など編集可能ステータスを想定(初期データ投入時 ID=1 のレコード作成前提)
    # 見積の作成者を記録するための外部キー
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="見積作成者")
    estimate_number = models.CharField('見積番号', max_length=50, unique=True)
    customer_name = models.CharField('顧客名（個人・会社）', max_length=100)
    vehicle_name = models.CharField('車種', max_length=100)
    is_fixed = models.BooleanField('確定フラグ', default=False)
    # 外税内税の切替・会計システム連携の際は IntegerField を DecimalField に変更検討
    total_price = models.IntegerField('見積時合計金額', default=0) #円単位・税込固定
    created_at = models.DateTimeField('作成日時', auto_now_add=True) # レコード作成時に自動で現在日時をセット
    updated_at = models.DateTimeField('更新日時', auto_now=True) # レコード更新時に自動で現在日時をセット
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, # 更新者を記録するための外部キー
    on_delete=models.PROTECT, # 更新者のユーザーレコードが削除されないように PROTECT を指定
    related_name='updated_estimates', # User モデルから見たときの逆参照名
    null=True, blank=True)# 更新者は必須ではないため null=True, blank=True を指定

# ステータスに応じて見積を自動ロック（業務ルールをモデル層で担保）
    def save(self, *args, **kwargs):
        # 例えば、status が「契約済み」「キャンセル済み」などの場合
        if self.estimate_status:
            self.is_fixed = self.estimate_status.is_fixed # ステータスの is_fixed によって見積をロックする業務ルールをモデル層で担保
        
        super().save(*args, **kwargs) # 親クラスの save() メソッドを呼び出して保存

    def __str__(self):
        return f"Estimate {self.estimate_number} for {self.customer_name}"

# 見積時合計金額を再計算して保存するメソッド
    def recalc_total_price(self):
        total = sum(item.subtotal for item in self.items.all())
        self.total_price = total
        self.save(update_fields=['total_price'])