from django.contrib import admin
from .models import Estimate,  EstimateItem

# 親(見積)画面の中に、子(見積詳細)を見積画面下方に「表形式(Inline)」で並べる
class EstimateItemInline(admin.TabularInline):
    model = EstimateItem
    extra = 2  # 前後サイズ違いの車両を考慮して空行を2行追加
    min_num = 1  # 最低1行は必須 (空見積防止)
    fields = ('tire', 'quantity', 'unit_price_at_estimate', 'subtotal')  # 表示項目
    readonly_fields = ('subtotal',)  #　小計は自動計算(編集不可)、誤入力を防ぐ目的で readonly に設定

# 業務入力（見積時単価を表示するメゾット)
@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
        list_display = ('estimate_number', 'customer_name', 'total_price',  'created_at')  # 管理画面の一覧表にどの項目を表示するか指定
        readonly_fields = ('total_price', 'created_at')  # 合計金額や作成日時を画面上で勝手に書き換えられないよう保護
        inlines = [EstimateItemInline]  # 表形式の子テーブルを見積の編集画面にドッキング

        # 画面上部に検索バー、画面右側に日付フィルター追加
        search_fields = ('estimate_number', 'customer_name')
        list_filter = ('created_at',)