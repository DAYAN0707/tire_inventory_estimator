from django.db import models

class Tire(models.Model):
    product_code = models.CharField('商品コード', max_length=50) # unique=True を付けると商品コード変更時 UPDATEできない！
    manufacturer = models.CharField('メーカー', max_length=50)
    brand = models.CharField('ブランド', max_length=50)
    size_raw = models.CharField('サイズ', max_length=20)

    unit_price = models.IntegerField('1本単価') # 円単位・税込固定
    set_price = models.IntegerField('4本特価', null=True, blank=True) # 円単位・税込固定

    reorder_point = models.IntegerField('発注点', null=True, blank=True) # 自動アラート対応(在庫<発注点のアラート設定であっても、発注点が-1はアラート不要)
    stock_qty = models.IntegerField('在庫数量', default=0) # 在庫数量は0以上
    
    description = models.TextField('商品紹介文', blank=True,help_text="検索・見積画面に表示される説明文")
    
    
    # タイヤの状態（廃盤・取扱停止中など）を管理するための外部キー
    tire_status = models.ForeignKey('inventory.TireStatus',on_delete=models.PROTECT,
                                    null=True,  #（一時的に空を許す）
    blank=True) #（一時的に空を許す）
    
    
    def __str__(self):
        return f"{self.manufacturer} {self.brand} {self.size_raw}"