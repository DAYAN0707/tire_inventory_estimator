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

#管理画面でメーカー,ブランド,サイズが何本あるか表示
    def __str__(self):
        return f"{self.manufacturer} {self.brand} {self.width}/{self.aspect_ratio}R{self.rim} {self.road_index}{self.speed_symbol}"
    
#在庫ステータス表示候補を3パターンに固定
class Inventory(models.Model):
    # --- 定数の定義 ---
    IN_STOCK = 'in_stock'
    BACKORDER = 'backorder'
    ORDERABLE = 'orderable'

    STATUS_CHOICES = (
        (IN_STOCK, '在庫あり'),
        (BACKORDER, '入荷待ち'),
        (ORDERABLE, '取寄可能'),
    )

    # タイヤ1種類に対して在庫情報は1つ（1対1）
    tire = models.OneToOneField(Tire, on_delete=models.CASCADE, related_name='inventory')
    
    total_quantity = models.IntegerField('店内全在庫', default=0)
    reserved_quantity = models.IntegerField('予約在庫', default=0)
    reorder_quantity = models.IntegerField('発注点', default=4, help_text='在庫がこの本数を下回ったら発注アラートを出します')


    status = models.CharField(
        '在庫状態',
        max_length=20,
        choices=STATUS_CHOICES,
        default=IN_STOCK
    )
# 管理画面で日本語表示
    class Meta:
        verbose_name = '在庫情報'
        verbose_name_plural = '在庫情報一覧'

# 有効在庫を計算するプロパティ
@property
def available_stock(self):
    return max(0, self.total_quantity - self.reserved_quantity)

#初期値は仮で4を設定、発注点は商品ごとに異なるため管理画面で個別調整
def __str__(self):
    return f"{self.tire.size}（有効在庫: {self.available_stock}）"