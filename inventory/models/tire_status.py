from django.db import models

class TireStatus(models.Model):
    status_name = models.CharField("ステータス名", max_length=30)
    # is_fixed は TireStatus には不要(販売中 → 取扱停止 → 再開も有り得る為)

    def __str__(self):
        return self.status_name