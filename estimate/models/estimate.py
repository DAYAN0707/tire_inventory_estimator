from django.db import models, transaction
from django.db.models import Sum
from django.conf import settings
from django.core.exceptions import ValidationError
from estimate.models.estimate_status import EstimateStatus
from .cost_master import CostMaster
from django.urls import reverse
from django.utils import timezone



# 見積の基本情報を管理するモデル
class Estimate(models.Model):
    # 持ち帰り or 取付作業ありの選択肢を追加
    class PurchaseType(models.TextChoices):
        TAKE_HOME = 'take_home', '持ち帰り'
        INSTALL = 'install', '交換作業'

    purchase_type = models.CharField(
        max_length=20,
        choices=PurchaseType.choices,
    )

    unit_price = models.IntegerField(default=0) # 
    tax_rate = models.DecimalField(max_digits=4, decimal_places=2, default=0.10)
    subtotal = models.IntegerField(default=0)
    tax_amount = models.IntegerField(default=0)

    
    # 見積の状態を管理する外部キー(例: 作成中、予約確定、キャンセル済みなど)
    estimate_status = models.ForeignKey(EstimateStatus, on_delete=models.PROTECT, related_name='estimates')
    # ステータスに応じて見積を自動ロック（業務ルールをモデル層で担保）
    is_fixed = models.BooleanField('確定フラグ', default=False)
    # 顧客名、車種などの基本情報を追加
    customer_name = models.CharField('顧客名（個人・会社）', max_length=100)
    vehicle_name = models.CharField('車種', max_length=100, blank=True, null=True)
    # 見積番号はユニークな文字列として管理（例: "EST-20240601-001" などの形式を想定）
    estimate_number = models.CharField('見積番号', max_length=50, unique=True)
    # 見積時合計金額を保存するフィールドを追加（円単位・税込固定）
    total_price = models.IntegerField('見積時合計金額', default=0)
    # 見積の作成者を記録するための外部キー
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, # User モデルへの外部キー
        on_delete=models.PROTECT, # 作成者のユーザーレコードが削除されないように PROTECT を指定
        verbose_name="見積作成者" # 管理画面などでの表示名
    )
    # 更新者を記録するための外部キー
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, # User モデルへの外部キー
        on_delete=models.PROTECT, # 更新者のユーザーレコードが削除されないように PROTECT を指定
        related_name='updated_estimates', # User モデルから見たときの逆参照名
        null=True,blank=True) # 更新者は必須ではないため null=True, blank=True を指定
    
    # 作成日時と更新日時を自動で管理するフィールド
    created_at = models.DateTimeField('作成日時', auto_now_add=True)
    updated_at = models.DateTimeField('更新日時', auto_now=True)

    def get_absolute_url(self):
        return reverse("estimate:estimate_detail", args=[self.pk])

    # 見積時合計金額を再計算して保存するメソッド
    def clean(self):
        # 取付作業ありの場合は車種必須
        if self.purchase_type == Estimate.PurchaseType.INSTALL and not self.vehicle_name:
            raise ValidationError('取付作業の場合は車種が必須です')
# フォームだけでなく、モデルの clean() メソッドでも同様のバリデーションを行うことで、管理画面やAPI等、どこから見積が作成・更新されてもこの業務ルールが担保される



    def _apply_install_charges(self):
        # 応急処置：インチ別工賃ロジック一時停止
        return



    # 取付作業が不要になったときに、見積データから工賃（諸費用）だけを自動で削除する
    def _remove_install_charges(self):
        from estimate.models import EstimateCharge

        EstimateCharge.objects.filter(
            estimate=self,
            charge_type=EstimateCharge.ChargeType.INSTALL
        ).delete() 


    # 最終的な合計金額を計算し直して、保存する
    def _recalculate_total(self):
        item_total = self.items.aggregate(
            total=Sum('subtotal')
        )['total'] or 0

        # 工賃や廃タイヤ処分料など）の合計を計算
        charge_total = self.charges.aggregate(
            total=Sum('amount')
        )['total'] or 0 

        # タイヤ代と諸費用を足して、この見積書の total_amount(最終合計金額)とする
        self.total_price = item_total + charge_total
        # 無限 save 防止
        super().save(update_fields=['total_price'])
        # 全部の項目を保存し直すのではなく total_amount(最終合計金額)だけデータベースに上書き



    # 見積アイテムの小計を合計し、見積全体の合計金額を再計算するメソッド
    def recalc_total_price(self):
        total = sum(item.subtotal for item in self.items.all())
        self.total_price = total
        self.save(update_fields=['total_price'])

    def __str__(self): return f"Estimate {self.estimate_number} for {self.customer_name}" # 管理画面等表示用
    
    def save(self, *args, **kwargs):
        if not self.estimate_number:
            today = timezone.now().strftime("%Y%m%d")
            last = Estimate.objects.filter(
                estimate_number__startswith=f"EST-{today}"
            ).count() + 1

            self.estimate_number = f"EST-{today}-{last:03d}"

        super().save(*args, **kwargs)


