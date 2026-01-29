from django.db import models

class Tire(models.Model):

    manufacturer = models.CharField('メーカー',max_length=50)
    brand = models.CharField('ブランド',max_length=50)
    pattern = models.CharField('パターン',max_length=50)

    size = models.CharField('サイズ表記',max_length=20)
    width = models.PositiveIntegerField('幅(mm)')
    aspect_ratio = models.PositiveIntegerField('偏平率(%)')
    rim = models.PositiveIntegerField('インチ(inch)')
    road_index = models.CharField('ロードインデックス',max_length=10, blank=True)
    speed_symbol = models.CharField('速度記号',max_length=5, blank=True)

    price_single = models.PositiveIntegerField('1本価格')
    price_set = models.PositiveIntegerField('4本特価')

    def __str__(self):
        return f"{self.manufacturer} {self.brand} {self.width}/{self.aspect_ratio}R{self.rim} {self.road_index}{self.speed_symbol}"
    

class Inventory(models.Model):
    STATUS_CHOICES = (
        ('in_stock', '在庫あり'),
        ('backorder', '入荷待ち'),
        ('orderable', '取寄可能'),
    )

    tire = models.OneToOneField(Tire,on_delete=models.CASCADE,related_name='inventory')

    quantity = models.PositiveIntegerField('在庫本数')
    reorder_point = models.PositiveIntegerField('発注点')

    status = models.CharField('在庫状態',max_length=20, choices=STATUS_CHOICES)

    def __str__(self):
        return f"{self.tire} ： 残り{self.quantity}本"