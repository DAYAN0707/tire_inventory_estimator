from django.db import models
from django.conf import settings

# 監査ログモデル
class AuditLog(models.Model):
    target_type = models.CharField(max_length=30) # 例: "Estimate", "Tire", "TireStatus" など
    target_id = models.IntegerField() # 監査対象のレコードID
    action = models.CharField(max_length=20) # 例: "CREATE", "UPDATE", "DELETE"
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT) # 監査ログの作成者（ユーザー）
    acted_at = models.DateTimeField(auto_now_add=True) # 監査ログの作成日時
    before_value = models.TextField(null=True, blank=True) # 変更前の値（JSONなどの形式で保存することを想定）
    after_value = models.TextField(null=True, blank=True) # 変更後の値（JSONなどの形式で保存することを想定）
    note = models.TextField(blank=True) # 任意のメモ欄（例: 変更理由など）

    class Meta:
        ordering = ['-acted_at'] # 監査ログは作成日時の降順で表示

    # 更新・削除不可のロジック
    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError("AuditLog は更新できません")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("AuditLog は削除できません")
    
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT) # 監査ログの作成者（ユーザー）