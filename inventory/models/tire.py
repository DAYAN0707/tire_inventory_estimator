from django.db import models
from django.db import models

class Brand(models.Model):
    #--- ブランド情報 ---
    name = models.CharField(max_length=100, unique=True, verbose_name="ブランド名")
    comment = models.TextField(blank=True, verbose_name="ブランド特徴コメント")

    def __str__(self):
        return self.name
from django.db import models

class Tire(models.Model):
    # --- 基本情報 ---
    product_code = models.CharField('商品コード', max_length=50) # unique=True を付けると商品コード変更時 UPDATEできない！
    manufacturer = models.CharField('メーカー', max_length=100)
    brand_link = models.ForeignKey('Brand', on_delete=models.SET_NULL, null=True, blank=True) # 新データ用のブランド外部キー
    brand = models.CharField(max_length=100) # 既存データ移行用or予備
    size_raw = models.CharField('サイズ', max_length=50)
    is_runflat = models.BooleanField(default=False)

    # --- 価格情報 ---
    unit_price = models.IntegerField('1本単価') # 円単位・税込固定
    set_price = models.IntegerField('4本特価', null=True, blank=True) # 円単位・税込固定
    cost_price = models.IntegerField('仕入れ値', null=True, blank=True) # 原価管理や利益率分析のために保持

    # --- 在庫管理・予約 ---
    stock_qty = models.IntegerField('実在庫', default=0) # お店に実際にある本数
    reserved_qty = models.IntegerField('予約確定数', default=0) # 🌟 予約(取置)が確定し、売約済みとなった本数
    reorder_point = models.IntegerField('発注点', default=0) # この数値を下回ったらアラート
    
    @property
    def effective_stock(self):
        """
        有効在庫 = 実在庫 - 予約確定数
        DBには保存せず、呼び出された瞬間に計算することでデータのズレを防ぎます
        """
        return self.stock_qty - self.reserved_qty

    @property
    def needs_reorder(self):
        """
        有効在庫が発注点を下回っているか判定
        発注点が 0 の場合は、在庫が 0 になった時点で True になります
        """
        return self.effective_stock <= self.reorder_point

    description = models.TextField('商品紹介文', blank=True, help_text="検索・見積画面に表示される説明文")
    
    # タイヤの状態（廃盤・取扱停止中など）を管理するための外部キー
    tire_status = models.ForeignKey(
        'inventory.TireStatus',
        on_delete=models.PROTECT,
        null=True, 
        blank=True
    )

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

    # 発注は「どのタイヤを」「いくつ」かが基本情報なので、タイヤへの外部キーと数量を持たせる
    tire = models.ForeignKey('Tire', on_delete=models.CASCADE, verbose_name="タイヤ")
    quantity = models.PositiveIntegerField("数量", default=4)  # デフォルトは1台分の4本
    status = models.CharField("状態", max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    
    # 価格改定があっても「発注時の金額」を記録しておくために必要
    cost_price_at_order = models.IntegerField("発注時仕入れ値", null=True, blank=True)
    
    # 発注者と日時の記録（誰がいつ発注したかを追跡できるようにするため）
    user = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, verbose_name="発注者")
    created_at = models.DateTimeField("発注日", auto_now_add=True)
    updated_at = models.DateTimeField("更新日", auto_now=True)

    class Meta:
        # 管理画面での表示名や並び順を指定
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