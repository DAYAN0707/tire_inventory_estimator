from django.db import models
from django.db import models

class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="ブランド名")
    comment = models.TextField(blank=True, verbose_name="ブランド特徴コメント")

    def __str__(self):
        return self.name

class Tire(models.Model):
    product_code = models.CharField('商品コード', max_length=50) # unique=True を付けると商品コード変更時 UPDATEできない！
    manufacturer = models.CharField('メーカー', max_length=100)
    brand_link = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True) # 新データ用のブランド外部キー
    brand = models.CharField(max_length=100) # 既存データ移行用or予備
    size_raw = models.CharField('サイズ', max_length=50)
    is_runflat = models.BooleanField(default=False) 

    unit_price = models.IntegerField('1本単価') # 円単位・税込固定
    set_price = models.IntegerField('4本特価', null=True, blank=True) # 円単位・税込固定

    reorder_point = models.IntegerField('発注点', null=True, blank=True) # 自動アラート対応(在庫<発注点のアラート設定であっても、発注点が-1はアラート不要)
    stock_qty = models.IntegerField('在庫数量', default=0) # 在庫数量は0以上
    
    description = models.TextField('商品紹介文', blank=True,help_text="検索・見積画面に表示される説明文")
    cost_price = models.IntegerField('仕入れ値', null=True, blank=True) # 仕入れ値は管理用で、見積計算には使用しない（原価管理や利益率分析のために保持）
    
    # タイヤの状態（廃盤・取扱停止中など）を管理するための外部キー
    tire_status = models.ForeignKey('inventory.TireStatus',on_delete=models.PROTECT,
                                    null=True,  #（一時的に空を許す）
    blank=True) #（一時的に空を許す）

    def __str__(self):
        # brand_linkがあればその名前を、なければ直書きのbrandを表示する
        brand_name = self.brand_link.name if self.brand_link else self.brand
        return f"{self.manufacturer} {brand_name} {self.size_raw}"



    def get_stock_status(self):
        """一覧画面用の在庫ステータス判定"""
        # 在庫が1本でもあれば「在庫あり」
        if self.stock_qty > 0:
            return {"text": "在庫あり", "color": "success", "is_available": True}
        
        # 在庫0かつ発注点が0なら「取寄可能」
        if self.reorder_point == 0:
            return {"text": "取寄可能", "color": "secondary", "is_available": True}
        
        # それ以外は「入荷待ち」
        return {"text": "入荷待ち", "color": "danger", "is_available": False}
    

class Order(models.Model):
    # ステータスの選択肢
    STATUS_CHOICES = [
        ('DRAFT', '仮発注'),
        ('CONFIRMED', '確定'),
        ('CANCELLED', '取消'),
    ]

    tire = models.ForeignKey('Tire', on_delete=models.CASCADE, verbose_name="タイヤ")
    quantity = models.PositiveIntegerField("数量", default=4)  # デフォルトは1台分の4本
    status = models.CharField("状態", max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    
    # 価格改定があっても「発注時の金額」を記録しておくために必要
    cost_price_at_order = models.IntegerField("発注時仕入れ値", null=True, blank=True)
    
    user = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, verbose_name="発注者")
    created_at = models.DateTimeField("発注日", auto_now_add=True)
    updated_at = models.DateTimeField("更新日", auto_now=True)

    class Meta:
        verbose_name = "発注"
        verbose_name_plural = "発注一覧"
        ordering = ['-created_at']

    # 🎯 確定後は「数量変更」を禁止するロジック
    def save(self, *args, **kwargs):
        if self.pk:  # すでにDBに保存されているデータの更新時
            original = Order.objects.get(pk=self.pk)
            if original.status == 'CONFIRMED' and self.quantity != original.quantity:
                raise ValueError("確定済みの発注数量は変更できません。変更が必要な場合は一度取り消してください。")
        super().save(*args, **kwargs)