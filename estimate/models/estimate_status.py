from django.db import models

# 見積の状態を管理するモデル
class EstimateStatus(models.Model):
    status_name = models.CharField('ステータス名', max_length=50)
    is_fixed = models.BooleanField('確定ステータス', default=False, help_text="このステータスの見積は編集不可") 
    # 見積確定後は変更不可とする為、View 依存にせず is_fixed によってロックする業務ルールをモデル層で担保

    def __str__(self):
        return self.status_name
