from django.db import models

class Estimate(models.Model):
    estimate_number = models.CharField('見積番号', max_length=50, unique=True)
    customer_name = models.CharField('顧客名', max_length=100)
    created_at = models.DateTimeField('作成日時', auto_now_add=True)

    def __str__(self):
        return f"Estimate {self.estimate_number} for {self.customer_name}"
