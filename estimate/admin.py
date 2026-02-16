from django.contrib import admin
from django.utils.html import format_html
from .models import Estimate,EstimateItem,EstimateStatus,ExpenseMaster

# 親(見積)画面の中に、子(見積詳細)を見積画面下方に「表形式(Inline)」で並べる
class EstimateItemInline(admin.TabularInline):
    model = EstimateItem
    extra = 2  # 前後サイズ違いの車両を考慮して空行を2行追加
    min_num = 1  # 最低1行は必須 (空見積防止)
    fields = ('tire', 'quantity', 'unit_price', 'subtotal')  # 表示項目
    readonly_fields = ('subtotal',)  #　小計は自動計算(編集不可)、誤入力を防ぐ目的で readonly に設定

# 見積確定(is_fixed=True)後は、明細(EstimateItem)の追加・変更・削除すべて禁止
# 見積履歴保全の為、admin 権限制御
    def has_add_permission(self, request, obj):
        if obj and obj.is_fixed:
            return False
        return True

    def has_change_permission(self, request, obj=None):
        if obj and obj.is_fixed:
            return False
        return True
    
    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_fixed:
            return False
        return True
    

# 見積入力画面（EstimateItem を Inline で入力可能にする）
@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
        list_display = ('estimate_number', 'customer_name','colored_status', 'total_price',  'created_at')  # 管理画面の一覧表にどの項目を表示するか指定
        readonly_fields = ('total_price', 'created_at')  # 合計金額や作成日時を画面上で勝手に書き換えられないよう保護
        inlines = [EstimateItemInline]  # 表形式の子テーブルを見積の編集画面にドッキング

        # 画面上部に検索バー、画面右側に日付フィルター追加
        search_fields = ('estimate_number', 'customer_name')
        list_filter = ('created_at',)

        def colored_status(self, obj):
        # 見積が確定している場合、新規追加を禁止
            if obj.status.is_fixed:
                return format_html('<span style="color: white; background-color: #d9534f; padding: 2px 6px; border-radius: 4px;">{}</span>',
obj.status.status_name) # 赤背景で強調表示
            return format_html('<span style="color: #333; background-color: #f0ad4e; padding: 2px 6px; border-radius: 4px;">{}</span>',
            obj.status.status_name) # 黄背景で表示

        colored_status.short_description = 'ステータス' # 管理画面の列見出し