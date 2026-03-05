from django.db import models

# 見積の状態を管理するモデル
class EstimateStatus(models.Model):
    status_name = models.CharField('ステータス名', max_length=50)
    is_fixed = models.BooleanField('確定ステータス', default=False, help_text="このステータスの見積は編集不可") 

    class Meta:
        verbose_name = "Estimate Status"
        verbose_name_plural = "Estimate Statuses"

    def __str__(self):
        return self.status_name