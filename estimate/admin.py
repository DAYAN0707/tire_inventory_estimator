from django.utils.html import format_html
from audit.models.audit_log import AuditLog
from estimate.services.usecase import recalc_estimate
from estimate.models.estimate_status import EstimateStatus

from django.contrib import admin
from .models import Estimate, EstimateItem, CostMaster, EstimateStatus ,EstimateCharge


# 親(見積)画面の中に、子(見積詳細)を見積画面下方に「表形式(Inline)」で並べる
class EstimateItemInline(admin.TabularInline):
    model = EstimateItem

    # 見積明細の入力フォームで、在庫数や在庫状況をリアルタイムに表示するためのカスタムメソッドを定義
    fields = (
        'tire',
        'quantity',
        'unit_price',
        'subtotal',
        'stock_status_display', 
    )

    # 小計と在庫状況は見積入力の際に自動計算される項目で、誤入力を防ぐために readonly に設定
    readonly_fields = (
        'unit_price',
        'subtotal',
        'stock_status_display',
    )

    extra = 2 # 前後サイズ違いの車両を考慮して空行を2行追加
    min_num = 1# 空見積防止のため、最低1行は必須とする

    # 在庫状況をリアルタイムに表示するカスタムメソッド
    def stock_status_display(self, obj):
        if not obj.pk:
            return "-"
        # 見積アイテムの stock_judgement() メソッドを呼び出して在庫状況を取得
        status = obj.stock_judgement()
        # 在庫数が見積本数以上ある場合は「在庫有」と緑色で表示
        if status == "在庫有":
            return format_html('<span style="color:green; font-weight:bold;">{}</span>', status)
        # 発注点がない場合は「取寄可能」とグレーで表示
        if status == "取寄可能":
            return format_html('<span style="color:gray;">{}</span>', status)
        # 在庫数が発注点以下・在庫数が見積本数以下の場合は「入荷待ち」と赤色で表示
        return format_html('<span style="color:red; font-weight:bold;">{}</span>', status)

    stock_status_display.short_description = "在庫状況"

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
    


class EstimateChargeInline(admin.TabularInline):
    model = EstimateCharge
    extra = 0
    fields = ("charge_type", "quantity", "unit_price", "subtotal")
    readonly_fields = ("subtotal",)


# 見積入力画面（EstimateItem を Inline で入力可能にする）
@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
        # 画面から入力を消して、自動セットにする項目を exclude に追加    
        exclude = ('created_by', 'updated_by')
        list_display = ("id", "estimate_number", "customer_name", "vehicle_name", "colored_status", "total_price", "created_at", "is_fixed") # 管理画面の一覧表にどの項目を表示するか指定
        readonly_fields = ('total_price', 'created_at', 'updated_at', 'is_fixed')  # 合計金額や作成日時を画面上で勝手に書き換えられないよう保護
        resource_class = None # 明示的にリソースがないことを指定（通常は自動生成されるが、見積はインポート・エクスポート対象外のため None を指定して明示的に無効化）
        fields = ('estimate_number', 'customer_name', 'vehicle_name', 'purchase_type', 'estimate_status', 'is_fixed', 'total_price', 'updated_at', 'created_at')
        inlines = [EstimateItemInline] # 表形式の子テーブルを見積の編集画面にドッキング

        # 画面上部に検索バー、画面右側に日付フィルター追加
        search_fields = ('estimate_number', 'customer_name', 'vehicle_name') # 見積番号と顧客名・車種で検索可能
        list_filter = ('created_at','purchase_type') # 作成日時と購入タイプで絞り込み可能
        # フォームのレイアウトをカスタマイズ（フィールドセットを定義して、関連する項目をグループ化）
        fields = ('estimate_number', 'customer_name', 'vehicle_name', 'purchase_type', 'estimate_status', 'is_fixed', 'total_price', 'updated_at', 'created_at') # 管理画面の入力フォームに表示する項目と順番を指定（created_by, updated_by は exclude で消しているため表示されない）

            # 新規作成時に request.user を created_by にセット
        def save_model(self, request, obj, form, change):
            if not change:  # 新規作成の時だけ
                obj.created_by = request.user
            super().save_model(request, obj, form, change)
            
            if not obj.status:
                obj.estimate_status = EstimateStatus.objects.get(status_name="作成中")
            super().save_model(request, obj, form, change)

            # 作成者・更新者などのセット
            if not change:
                obj.created_by = request.user
                obj.updated_by = request.user

            recalc_estimate(obj)


        def get_changeform_initial_data(self, request):# 新規作成画面を開いた瞬間、見積ステータスの初期値を「作成中」にセットするためのオーバーライド
            initial = super().get_changeform_initial_data(request)
            try:
                initial['estimate_status'] = EstimateStatus.objects.get(status_name="作成中") # デフォルトの 作成中ステータス をセット
            except EstimateStatus.DoesNotExist:
                pass
            return initial
        

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


@admin.register(EstimateStatus)
class EstimateStatusAdmin(admin.ModelAdmin):
    list_display = ("id", "status_name", "is_fixed")


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