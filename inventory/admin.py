from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum, Q  # 集計（Sum）に必要
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from .models import Tire, TireStatus

# 予約確定の見積に紐づく見積明細の件数をカウントするための定数(将来の拡張性のため、ハードコードせず定数化)
RESERVED_STATUS = '予約確定'

#  Tire モデル用のリソースクラス定義(インポート・エクスポートの設定)
class TireResource(resources.ModelResource):
    class Meta:
        model = Tire
        import_id_fields = ('product_code',) # 一意の識別子として商品コードを使用
        fields = (
            'product_code', 'manufacturer', 'brand', 'size_raw', 
            'unit_price', 'set_price', 'reorder_point', 'stock_qty',)  # インポート・エクスポートするフィールド

# 発注点は在庫管理の重要な指標なので、インポート・エクスポートの対象に含める
# 在庫戦略フィルタ（0やNULLの汚れに対応するため、カスタムフィルタを定義）も admin.py に追加
class ReorderPointFilter(admin.SimpleListFilter):
    #在庫管理のためのカスタムフィルタ（発注点設定の有無で絞り込み）
    title = '在庫戦略' # 管理画面のフィルタ見出し(取寄専用(NULL/0),常備在庫(1以上))
    parameter_name = 'reorder_point'

    # フィルタの選択肢を定義(発注点が0またはNULLのものを「取寄専用」、1以上のものを「常備在庫」として表示)
    def lookups(self, request, model_admin):
        return (
            ('unset', '取寄専用 (0 / 未設定)'), ('set', '常備在庫 (1以上)'), )

    # フィルタの選択に応じてクエリセットを絞り込むロジック
    def queryset(self, request, queryset):
        # 「未設定」＝ NULL または 0（取り寄せ専用）
        if self.value() == 'unset':
            return queryset.filter(
                Q(reorder_point__isnull=True) | Q(reorder_point=0) # reorder_point が NULL または 0 のものを抽出
        )
        # 「設定あり」＝ 1以上（常備在庫）
        if self.value() == 'set':
            return queryset.filter(reorder_point__gt=0) # 発注点が0より大きいものを抽出
        return queryset # フィルタ未選択時は全件表示


    # マスタ管理（タイヤ・在庫）
# ImportExportModelAdmin を継承、インポート・エクスポート機能を有効化
@admin.register(Tire)
class TireAdmin(ImportExportModelAdmin):
    resource_class = TireResource # 先に定義した TireResource をリソースクラスとして指定 
    
    # パフォーマンス最適化のため、関連するタイヤの状態を一括取得するようクエリセットをオーバーライド
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('tire_status')# リスト表示でのアクセスを高速化
    
    # リスト表示項目
    list_display = (
        'brand_display',   # ブランドとサイズをまとめた列(廃盤判定込)
        'reserved_info',   # 予約数表示(見積連動)
        'stock_status',    # 有効在庫(取り寄せ・赤字判定込み)
        'reorder_point',   # 発注点(分析の閾値)
        'formatted_unit_price', 
        'formatted_set_price',
        'order_button', # 操作(発注)
    )
    # 検索バー設定　(メーカー、ブランド、サイズ、商品コードで部分一致検索可能)
    search_fields = ('manufacturer', 'brand', 'size_raw', 'product_code')
    # フィルタ設定(メーカー：ブリヂストン 且つ 在庫戦略：設定あり(常備品)などの絞り込みが可能)
    list_filter = ('manufacturer', 'brand', ReorderPointFilter) # 在庫戦略フィルタ追加


    # タイヤの状態(廃盤・取扱停止)を管理するための外部キーをリスト表示に追加
    def brand_display(self, obj):
        if obj.tire_status and not obj.tire_status.is_active: # タイヤのステータスが非アクティブ(廃盤・取扱停止)ならグレー表示
            return format_html(
                '<span style="color:#999;">'
                '<b>{}</b><br>' # ブランド名を太字・垂直方向に情報整理(<span>では全て横並びなので<br>でブランド名とサイズを改行して表示)
                '<small>{}</small><br>' # サイズを小さく表示
                '<small>（販売終了）</small>' # 廃盤・取扱停止の注釈を追加
                '</span>',
                obj.brand,
                obj.size_raw
            )
        # 通常の販売中タイヤ(アクティブ)なら通常の色で、ブランドとサイズだけ表示
        return format_html(
            '<b>{}</b><br><small>{}</small>', # 改行、ブランド太字、サイズ小
            obj.brand,
            obj.size_raw
        )
    brand_display.short_description = "タイヤ情報" # 管理画面の列見出し

    # タイヤの状態(廃盤・取扱停止)を管理するための外部キーをリスト表示に追加
    def reserved_info(self, obj):
    # 予約確定の見積明細に紐づく件数と数量をカウントして表示
        qs = obj.estimate_items.filter(
            estimate__estimate_status__status_name=RESERVED_STATUS
        )

        # 予約数と予約数量を集計(予約数は見積件数、予約数量は見積明細の数量合計)
        reserved_count = qs.values('estimate').distinct().count()
        reserved_qty = qs.aggregate(total=Sum('quantity'))['total'] or 0
        # 予約数がある場合は件数と数量をオレンジ色で表示、0件の場合は「—」で表示
        if reserved_count:
            return format_html(
                '<span style="color: orange; font-weight: bold;">'
                '{}件<br><small>({}本)</small>' # 件数と数量を改行して表示
                '</span>', 
                reserved_count, reserved_qty
            )
        return '—'
    reserved_info.short_description = "予約状況"

    # 在庫未登録にも耐えるよう修正
    def stock_status(self, obj):
        # 業務ルール：発注点がない場合は「取り寄せ」
        if obj.reorder_point in (None, 0):
            return format_html('<span style="color: gray;">取り寄せ</span>') # グレーで「取り寄せ」と表示
        
        # 在庫数取得(在庫数は Tire モデルのフィールドなので、直接 obj.stock_qty でアクセス)
        current = obj.stock_qty or 0
        if current < obj.reorder_point:
            return format_html('<b style="color: red; font-size: 1.1em;">{:,}</b>',current) # 在庫不足は赤字で強調表示
        return format_html('<b>{:,}</b>', current)
    stock_status.short_description = "有効在庫"

    def formatted_unit_price(self, obj):
        return f"{obj.unit_price:,}" if obj.unit_price else "0"
    formatted_unit_price.short_description = "1本価格"

    def formatted_set_price(self, obj):
        if obj.set_price is None:
            return "—"
        return f"{obj.set_price:,}"
    formatted_set_price.short_description = "4本特価"

    #発注ボタンの表示
    def order_button(self, obj):
        return format_html(
            '<a class="button" style="background-color: #2a7da3; color: white; padding: 4px 12px; border-radius: 4px; text-decoration: none;" '
            'href="#" onclick="alert(\'{}を発注しました\'); return false;">発注</a>', # 将来は実際の発注処理にリンクさせる予定
            obj.brand
        )
    order_button.short_description = "操作" # 管理画面の列見出し