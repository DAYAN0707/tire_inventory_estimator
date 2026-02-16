from django.db import models

class ExpenseMaster(models.Model):
    item_name = models.CharField("項目名", max_length=50)
    inch_size = models.IntegerField("インチ", null=True, blank=True)
    unit_price = models.IntegerField("単価")
    category = models.CharField("カテゴリ", max_length=20)

    def __str__(self):
        return self.item_name
