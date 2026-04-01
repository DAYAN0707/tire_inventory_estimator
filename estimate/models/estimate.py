from django.db.models import Sum, Max
from django.conf import settings
from django.core.exceptions import ValidationError
from .masters.estimate_status import EstimateStatus
from django.urls import reverse
from django.utils import timezone
from django.db import models, transaction
from django.contrib import admin
from datetime import timedelta # 日付計算用


# 見積の基本情報を管理するモデル
class Estimate(models.Model):
    # 持ち帰り or 取付作業ありの選択肢を追加
    class PurchaseType(models.TextChoices):
        TAKE_HOME = 'take_home', '持ち帰り'
        INSTALL = 'install', '交換作業'
        

    purchase_type = models.CharField(
        max_length=20,
        choices=PurchaseType.choices,
        default=PurchaseType.INSTALL,
        verbose_name="購入区分"
    )

    subtotal = models.IntegerField(default=0)

    
    # 見積の状態を管理する外部キー(例: 作成中、予約確定、キャンセル済みなど)
    estimate_status = models.ForeignKey(EstimateStatus, on_delete=models.PROTECT, related_name='estimates', default=1)
    # ステータスに応じて見積を自動ロック（業務ルールをモデル層で担保）
    is_fixed = models.BooleanField('確定フラグ', default=False)
    # 顧客名、車種などの基本情報を追加
    customer_name = models.CharField('顧客名（個人・会社）', max_length=100)
    vehicle_name = models.CharField('車種', max_length=100, blank=True, null=True)
    # 見積番号はユニークな文字列として管理（例: "EST-20240601-001" などの形式を想定）
    estimate_number = models.CharField('見積番号', max_length=20, unique=True, blank=True, db_index=True, help_text='空のまま保存すると "EST-YYYYMMDD-001" 形式で自動採番されます')
    # 見積時合計金額を保存するフィールドを追加（円単位・税込固定）
    total_price = models.IntegerField('見積時合計金額', default=0)
    # 見積の作成者を記録するための外部キー
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, # User モデルへの外部キー
        on_delete=models.PROTECT, # 作成者のユーザーレコードが削除されないように PROTECT を指定
        verbose_name='見積作成者' # 管理画面などでの表示名
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

    # --- 【新規追加】見積書の有効期限を計算するプロパティ ---
    @property
    def valid_until(self):
        """作成日時から30日後の日付を計算して返す"""
        if self.created_at:
            return self.created_at + timedelta(days=30)
        # まだ保存されていない（created_atがない）場合は、今日から30日後を暫定で返す
        return timezone.now() + timedelta(days=30)

    def save(self, *args, **kwargs):
        
        # 見積番号は日付ベースの連番で採番
        # 同時アクセス時の番号重複を防ぐ為、transaction.atomic() と select_for_update() を使いロックする実装
        if not self.estimate_number:
            # 1. サーバー設定（日本時間）に基づいた今日の日付を取得
            # timezone.localdate() を使うことで、海外時間との時差問題回避
            today_str = timezone.localdate().strftime('%Y%m%d')
            
            ## 2. データベースをロックして「最新の番号」を安全に取得
            # このブロック内は1つのDBトランザクション(途中で他の処理が割り込めない)
            with transaction.atomic():
                # select_for_update() で、銀行レベルのロック!!(このレコードは処理が終わるまで他の処理が触れない)
                last_estimate = (
                    Estimate.objects
                    .select_for_update()
                    .filter(estimate_number__startswith=f"EST-{today_str}")
                    .aggregate(Max("estimate_number"))
                )

                last_number = last_estimate["estimate_number__max"]

                if last_number:
                    # 最新番号（例: EST-20260305-002）の末尾3文字を取り出して+1
                    seq = int(last_number[-3:]) + 1
                else:
                    # 今日最初の発行なら 1
                    seq = 1

            # 3. 新しい番号をセット (例: EST-20260305-003)
                self.estimate_number = f"EST-{today_str}-{seq:03}"

        # 4. 実際の保存を実行
        super().save(*args, **kwargs)


    # 見積アイテムの小計を合計し、見積全体の合計金額を再計算するメソッド
    def recalc_total_price(self):

        # タイヤ代と諸費用を合算して合計金額を更新
        # from estimate.services.calculator import sync_estimate_charges
        # 1. 諸費用の自動生成（確定前のみ）
        # if not self.is_fixed:
            # sync_estimate_charges(self)

        # タイヤ代の合計
        item_total = sum(item.subtotal for item in self.items.all()) or 0
        # 諸費用の合計
        charge_total = sum(charge.subtotal for charge in self.charges.all()) or 0

        # 日本の商売では円単位（整数）が普通なので、計算の最後に int() でくくる
        self.total_price = int(item_total + charge_total)
        # save()を呼ぶと無限ループになるのでupdateを使用
        Estimate.objects.filter(pk=self.pk).update(total_price=self.total_price)



    def __str__(self): return f"Estimate {self.estimate_number} for {self.customer_name}" # 管理画面等表示用




    # この見積データの「詳細表示画面」のURLを自動生成して返すメソッド
    # 管理画面の「サイトで表示」ボタンや、テンプレート内でのリンク作成で使用
    def get_absolute_url(self):
        # reverse関数を使うことで、urls.pyで定義した名前（estimate:estimate_detail）から
        # 実際のURL（例: /estimate/123/）を逆引き
        return reverse("estimate:estimate_detail", args=[self.pk])

    # 見積時合計金額を再計算して保存するメソッド
    def clean(self):
        # 保存ボタンを押した時に実行される強力なバリデーション
        super().clean()

        # 取付作業ありの場合は車種必須
        if self.purchase_type == "install" and not self.vehicle_name:
            raise ValidationError('取付作業の場合は車種が必須です')

        # 【新規】保存済みのデータがある場合のみ、台数・本数制限をチェック
        if self.pk and self.purchase_type == "install":
            item_kinds = self.items.count()
            if item_kinds > 2:
                raise ValidationError(f"【台数制限エラー】作業予約は1台分（前後サイズ違いのお車は最大2サイズ可）までです。")
                
            total_qty = sum(item.quantity for item in self.items.all())
            if total_qty > 8:
                raise ValidationError(
                    f"【本数制限エラー】1台分（最大8本）を超えています。"
                )

# フォームだけでなく、モデルの clean() メソッドでも同様のバリデーションを行うことで、管理画面やAPI等、どこから見積が作成・更新されてもこの業務ルールが担保される