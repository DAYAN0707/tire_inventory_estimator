from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from .models import Tire
from import_export import resources

class TireResource(resources.ModelResource):
    class Meta:
        model = Tire
        import_id_fields = ('product_code',)
        fields = (
            'product_code', 'manufacturer', 'brand', 'size_raw', 
            'unit_price', 'set_price', 'reorder_point', 'stock_qty', 
            'purchase_price')

@admin.register(Tire)
class TireAdmin(ImportExportModelAdmin):
    resource_class = TireResource

    actions_on_top = False      # 上部のバー削除
    actions_on_bottom = True    # 下にバーを表示

    list_display = (
        'brand_display',  # ブランドとサイズをまとめた列
        'stock_qty',       # 実在庫
        'stock_status',    # 有効在庫（赤字判定）
        'reorder_point',   # 定数
        'formatted_unit_price',      # 販売単価
        'formatted_set_price',       # 4本特価　
        'order_button',     # 操作（発注）
        'formatted_purchase_price',   # 仕入れ値
    )

    def formatted_unit_price(self, obj):
        return f"{obj.unit_price:,}" if obj.unit_price else "0"
    formatted_unit_price.short_description = "1本価格"

    def formatted_set_price(self, obj):
        return f"{obj.set_price:,}" if obj.set_price else "0"
    formatted_set_price.short_description = "4本特価"

    def formatted_purchase_price(self, obj):
        return f"{obj.purchase_price:,}" if obj.purchase_price else "0"
    formatted_purchase_price.short_description = "仕入れ値"


    def brand_display(self, obj):
        return format_html('<b>{}</b><br><small>{}</small>', obj.brand, obj.size_raw)
    brand_display.short_description = "タイヤ情報"

    def stock_status(self, obj):
        limit = obj.reorder_point or 0
        current = obj.stock_qty or 0
        
        # 在庫不足（赤字 ＋ 太字 ＋ 少し大きく）
        if current < limit:
            return format_html(
                '<b style="color: red; font-weight: bold; font-size: 1.2em;">{}</b>', 
                current
            )
        
        # 通常時（太字のみ）
        return format_html('<b style="font-weight: bold;">{}</b>', current)
    stock_status.short_description = "有効在庫"

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


