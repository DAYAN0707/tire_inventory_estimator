from django.contrib import admin
from django.utils.html import format_html
from .models import Estimate,EstimateItem,EstimateStatus,ExpenseMaster
from audit.models.audit_log import AuditLog

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
        # 画面から入力を消して、自動セットにする項目を exclude に追加    
        exclude = ('created_by', 'updated_by')
        list_display = ('estimate_number', 'customer_name','colored_status', 'total_price',  'created_at')  # 管理画面の一覧表にどの項目を表示するか指定
        readonly_fields = ('total_price', 'created_at')  # 合計金額や作成日時を画面上で勝手に書き換えられないよう保護
        inlines = [EstimateItemInline]  # 表形式の子テーブルを見積の編集画面にドッキング

        # 画面上部に検索バー、画面右側に日付フィルター追加
        search_fields = ('estimate_number', 'customer_name')
        list_filter = ('created_at',)
        # フォームのレイアウトをカスタマイズ（フィールドセットを定義して、関連する項目をグループ化）
        fields = ('estimate_number', 'customer_name', 'estimate_status', 'is_fixed', 'total_price', 'created_at') # 管理画面の入力フォームに表示する項目と順番を指定（created_by, updated_by は exclude で消しているため表示されない）
        readonly_fields = ('total_price', 'created_at') # 合計金額や作成日時を画面上で勝手に書き換えられないよう保護

        def get_changeform_initial_data(self, request):# 新規作成画面を開いた瞬間、見積ステータスの初期値を「作成中」にセットするためのオーバーライド
            initial = super().get_changeform_initial_data(request)
            try:
                initial['estimate_status'] = EstimateStatus.objects.get(is_fixed=False) # デフォルトの 作成中ステータス をセットする安全策(マスタにない場合は空のまま)
            except EstimateStatus.DoesNotExist:
                pass
            return initial
        

        # 見積確定後は変更不可とするため、save_model() をオーバーライドして、見積の状態に応じて is_fixed を自動セットする業務ルールをモデル層で担保
        def save_model(self, request, obj, form, change):
            # 新規作成時は作成者をセット
            if not change:
                obj.created_by = request.user
                # 見積の状態が未設定の場合は、デフォルトの「作成中」ステータスをセットする安全策(マスタにない場合は空のまま)
                if not obj.estimate_status_id:
                    try:
                        obj.estimate_status = EstimateStatus.objects.get(status_name="作成中")
                    except EstimateStatus.DoesNotExist:
                        pass # マスタがない場合の安全策
            # 更新時は常に更新者をセット
            obj.updated_by = request.user
            # 見積の状態が「契約済み」「キャンセル済み」などの場合、自動的に is_fixed を True にセットしてロックする業務ルールをモデル層で担保
            if obj.estimate_status and obj.estimate_status.is_fixed:
                obj.is_fixed = True
            super().save_model(request, obj, form, change)

        # 見積の状態に応じてステータスを色分けして表示するカスタムメソッド
        def colored_status(self, obj):
            status = obj.estimate_status
            # 万が一ステータスが設定されていない場合の安全策
            if not status:
                return "—"
            # ステータスの is_fixed によって色分け（例：確定ステータスは赤、未確定ステータスはオレンジ）
            if status.is_fixed:
                return format_html(
                    '<span style="color: white; background-color: #d9534f; padding: 2px 6px; border-radius: 4px;">{}</span>',
                    status.status_name
                )
            return format_html(
                '<span style="color: #333; background-color: #f0ad4e; padding: 2px 6px; border-radius: 4px;">{}</span>',
                status.status_name
            )
        colored_status.short_description = 'ステータス' # 管理画面の列見出し


# タイヤの状態(廃盤・取扱停止)を管理するための外部キーをリスト表示に追加
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    readonly_fields = [f.name for f in AuditLog._meta.fields] # すべてのフィールドを読み取り専用に設定
    # 管理画面上での追加・変更・削除をすべて禁止
    def has_add_permission(self, request):
        return False
    # 管理画面上での変更・削除をすべて禁止
    def has_change_permission(self, request, obj=None):
        return False
    # 管理画面上での削除をすべて禁止
    def has_delete_permission(self, request, obj=None):
        return False
    
    # 監査ログはシステムが自動で記録するものであるため、管理画面からの編集は一切禁止する方針
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user # 新規作成時は作成者をセット

            if not obj.estimate_status_id:
                obj.estimate_status = EstimateStatus.objects.get(is_fixed=False)# デフォルトの 作成中ステータス をセットする安全策(マスタにない場合エラーになるが、監査ログは必ず見積と紐づく為、見積ステータスがない＝マスタがないケースは想定しない)

        obj.updated_by = request.user # 更新時は常に更新者をセット
        super().save_model(request, obj, form, change)