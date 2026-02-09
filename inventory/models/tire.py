from django.db import models

class Tire(models.Model):
    product_code = models.CharField('商品コード', max_length=50, unique=True)
    manufacturer = models.CharField('メーカー', max_length=50)
    brand = models.CharField('ブランド', max_length=100)
    size_raw = models.CharField('サイズ', max_length=20)

    unit_price = models.IntegerField('1本価格')
    set_price = models.IntegerField('4本特価')
    reorder_point = models.IntegerField('定数', default=4)

    def __str__(self):
        return f"{self.manufacturer} {self.brand} {self.size_raw}"