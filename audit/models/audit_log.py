from django.db import models
from django.conf import settings

# 監査ログモデル
class AuditLog(models.Model):
    # 監査対象の種別定義
    TARGET_TYPE_CHOICES = [
        ('estimate', '見積'),
        ('tire', 'タイヤ'),
        ('order', '発注'),
    ]

    # アクション種別の定義
    ACTION_CHOICES = [
        ('reserve_confirm', '予約確定'),
        ('reserve_cancel', '予約キャンセル'),
        ('order_create', '発注'),
        ('order_cancel', '発注取消'),
        ('status_change', 'ステータス変更'),
    ]

    # target_type + target_id でどのデータのログかを特定
    target_type = models.CharField(max_length=30, choices=TARGET_TYPE_CHOICES) # 例: "Estimate", "Tire" など
    target_id = models.PositiveIntegerField() # 監査対象のレコードID（正の整数に限定）

    action = models.CharField(max_length=50, choices=ACTION_CHOICES) # 例: "reserve_confirm" など
    
    # 監査ログの作成者（ユーザー）
    # アドバイスに従い、ユーザーが削除されてもログが消えないように SET_NULL に設定
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    ) 

    acted_at = models.DateTimeField(auto_now_add=True) # 監査ログの作成日時

    # 変更前後の値（JSONFieldにすることで、後からプログラムで解析しやすくする）
    before_value = models.JSONField(null=True, blank=True) # 変更前の値
    after_value = models.JSONField(null=True, blank=True) # 変更後の値
    
    note = models.TextField(blank=True) # 任意のメモ欄
    ip_address = models.GenericIPAddressField(null=True, blank=True) # 操作時のIPアドレス

    class Meta:
        ordering = ['-acted_at'] # 監査ログは作成日時の降順で表示
        verbose_name = "監査ログ"
        verbose_name_plural = "監査ログ一覧"
        # アドバイスに従い、検索速度向上のためのインデックスを貼る
        indexes = [
            models.Index(fields=['target_type', 'target_id']),
            models.Index(fields=['action']),
            models.Index(fields=['acted_at']),
        ]

    # 表示用のプロパティ（管理画面や一覧で見やすくするため）
    @property
    def target_label(self):
        return f"{self.get_target_type_display()}(ID:{self.target_id})"

    # 更新・削除不可のロジック
    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError("AuditLog は更新できません")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("AuditLog は削除できません")

    def __str__(self):
        # 日時や操作対象がひと目で分かる形式にする
        return f"{self.acted_at:%Y-%m-%d %H:%M} | {self.actor} | {self.get_action_display()} | {self.target_label}"