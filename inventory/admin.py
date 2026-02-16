from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from .models import Tire, TireStatus
from import_export import resources

#  Tire モデル用のリソースクラスを定義
class TireResource(resources.ModelResource):
    class Meta:
        model = Tire
        import_id_fields = ('product_code',) # 一意の識別子として商品コードを使用
        fields = (
            'product_code', 'manufacturer', 'brand', 'size_raw', 
            'unit_price', 'set_price', 'reorder_point',)  # インポート・エクスポートするフィールド

# マスタ管理（タイヤ・在庫）
# ImportExportModelAdmin を継承、インポート・エクスポート機能を有効化
@admin.register(Tire)
class TireAdmin(ImportExportModelAdmin):
    resource_class = TireResource

    actions_on_top = False      # 上部のバーを非表示
    actions_on_bottom = True    # 下にバーを表示

    list_display = (
        'brand_display',  # ブランドとサイズをまとめた列
        'stock_status',    # 有効在庫（赤字判定）
        'reorder_point',   # 定数
        'formatted_unit_price',      # 販売単価
        'formatted_set_price',       # 4本特価　
        'order_button',     # 操作(発注)
    )

    def formatted_unit_price(self, obj):
        return f"{obj.unit_price:,}" if obj.unit_price else "0"
    formatted_unit_price.short_description = "1本価格"

    def formatted_set_price(self, obj):
        return f"{obj.set_price:,}" if obj.set_price else "0"
    formatted_set_price.short_description = "4本特価"

    def brand_display(self, obj):
        return format_html('<b>{}</b><br><small>{}</small>', obj.brand, obj.size_raw)
    brand_display.short_description = "タイヤ情報"

    #  在庫未登録にも耐えるよう修正
    def stock_status(self, obj):
        # 発注点未設定
        if obj.reorder_point is None:
            return format_html('<span style="color: gray;">未設定</span>') # グレー表示  
        
        inventory = getattr(obj, 'inventory', None)
        if not inventory:
            return format_html('<span style="color: gray;">未登録</span>')

        limit = obj.reorder_point
        current = obj.stock_qty # 有効在庫

        # 在庫不足（赤字 ＋ 太字 ＋ 少し大きく）
        if current < limit:
            return format_html(
            '<b style="color: red; font-weight: bold; font-size: 1.2em;">{:,}</b>',current) #数値フォーマットを在庫にも統一

        # 通常時（太字のみ）
        return format_html('<b style="font-weight: bold;">{:,}</b>', current)
    stock_status.short_description = "有効在庫"

    # 発注ボタンの表示
    def order_button(self, obj):
        return format_html(
            '<a class="button" style="background-color: #2a7da3; color: white; padding: 4px 12px; border-radius: 4px; text-decoration: none;" '
            'href="#" onclick="alert(\'{}を発注しました\'); return false;">発注</a>',
            obj.brand
        )
    order_button.short_description = "操作"



    # 1. 検索バー
    # メーカー、ブランド、サイズ、商品コードで検索可能に
    search_fields = ('manufacturer', 'brand', 'size_raw', 'product_code')

    # 2. クリックでメーカー絞込
    list_filter = ('manufacturer', 'brand')


