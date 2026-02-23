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
        'stock_qty',       # 在庫数量表示
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
            # 廃盤・取扱停止のタイヤはグレーでブランドとサイズを表示し、さらに「販売終了」の文言を追加してわかりやすくする
            return format_html(
                '<span style="color:#999;"><b>{}</b><br><small>{}</small><br><small>（販売終了）</small></span>',
                obj.brand,
                obj.size_raw,
            )
        # 通常の販売中タイヤ(アクティブ)なら通常の色で、ブランドとサイズだけ表示
        return format_html(
            '<b>{}</b><br><small>{}</small>', # 改行、ブランド太字、サイズ小
            obj.brand,
            obj.size_raw,
        )
    
    brand_display.short_description = "タイヤ情報" # 管理画面の列見出し


    # タイヤの状態(廃盤・取扱停止)を管理するための外部キーをリスト表示に追加
    def reserved_info(self, obj):
    # 1.予約確定の見積明細に紐づく件数と数量をカウントして表示
        qs = obj.estimate_items.filter(
            estimate__estimate_status__status_name=RESERVED_STATUS
        )

        # 2.件数が0の場合は「—」を表示して終了
        reserved_count = qs.values('estimate').distinct().count()
        if reserved_count == 0:
            return '—'

        # 3.件数が1以上ある場合は、予約数量もカウントして表示（例: 3件(12本)
        reserved_qty = int(qs.aggregate(total=Sum('quantity'))['total'] or 0)

        # 4.件数と数量をフォーマットして表示 (例: 3件(12本))
        reserved_qty_display = f"{reserved_qty:,}"
        # 件数をオレンジ色で強調表示、数量を小さく表示、カンマ区切りで見やすく表示
        return format_html(
            '<span style="color: orange; font-weight: bold;">'
            '{}件<br><small>({}本)</small>'
            '</span>',
            reserved_count, # 件数をオレンジ色で強調表示
            reserved_qty_display # 予約数量を小さく表示、カンマ区切りで見やすく表示
        )
        
    reserved_info.short_description = "予約状況" # 管理画面の列見出し


    # 在庫未登録にも耐えるよう修正
    def stock_status(self, obj):
        # 在庫が1本以上ある場合は「在庫あり」と緑色で表示
        if obj.stock_qty > 0:
            return format_html('<span style="color: green;">{}</span>', '在庫あり')
        # 発注点がない場合は「取り寄せ」とグレーで表示(定数0 → 常備しない → 取寄専用の業務ルールをモデル層で担保)
        if obj.reorder_point in (None, 0):
            return format_html('<span style="color: gray;">{}</span>', '取り寄せ') # グレーで「取り寄せ」と表示
        # 在庫数が0で発注点がある場合は「入荷待ち」と赤色で表示
        return format_html('<span style="color: red;">{}</span>', '入荷待ち')
        

    def formatted_unit_price(self, obj): # 在庫未登録にも耐えるよう修正
        return f"{obj.unit_price:,}" if obj.unit_price else "0" # カンマ区切りで表示、unit_price が 0 の場合は「0」と表示
    formatted_unit_price.short_description = "1本価格" # 管理画面の列見出し

    def formatted_set_price(self, obj): # 在庫未登録にも耐えるよう修正
        if obj.set_price is None:
            return "—"
        return f"{obj.set_price:,}" # カンマ区切りで表示、set_price が None の場合は「—」を表示
    formatted_set_price.short_description = "4本特価" # 管理画面の列見出し

    #発注ボタンの表示
    def order_button(self, obj):
        return format_html(
            '<a class="button" style="background-color: #2a7da3; color: white; padding: 4px 12px; border-radius: 4px; text-decoration: none;" '
            'href="#" onclick="alert(\'{}を発注しました\'); return false;">発注</a>', # 将来は実際の発注処理にリンクさせる予定
            obj.brand
        )
    order_button.short_description = "操作" # 管理画面の列見出し