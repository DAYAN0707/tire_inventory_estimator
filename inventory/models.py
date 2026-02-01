from django.db import models

class Tire(models.Model):
    product_code = models.CharField('商品コード', max_length=50, unique=True)
    manufacturer = models.CharField('メーカー', max_length=50)
    brand = models.CharField('ブランド', max_length=100)
    size_raw = models.CharField('サイズ', max_length=20)

    unit_price = models.IntegerField('1本価格')
    set_price = models.IntegerField('4本特価')
    reorder_point = models.IntegerField('定数', default=4)
    stock_qty = models.IntegerField('実在庫', default=0)
    purchase_price = models.IntegerField('仕入れ値', default=0)

    def __str__(self):
        return f"{self.manufacturer} {self.brand} {self.size_raw}"


class Inventory(models.Model):
    tire = models.OneToOneField(
        Tire,
        on_delete=models.CASCADE,
        related_name='inventory'
    )

    total_quantity = models.IntegerField('総在庫数', default=0)
    reserved_quantity = models.IntegerField('予約在庫', default=0)
    reorder_point = models.IntegerField('定数', default=4)

    @property
    def available_stock(self):
        return self.total_quantity - self.reserved_quantity

    def __str__(self):
        return f"{self.tire}（在庫 {self.available_stock}）"

