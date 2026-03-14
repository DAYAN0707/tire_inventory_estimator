from django.contrib import admin, messages
from django import forms
from django.utils.html import format_html
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from estimate.models import Estimate, EstimateItem, EstimateCharge, EstimateStatus, ChargeMaster
from estimate.services.usecase import recalc_estimate, validate_estimate_rules
from audit.models.audit_log import AuditLog
from django.forms.models import BaseInlineFormSet



class EstimateItemInlineFormSet(BaseInlineFormSet):
    def clean(self):
        # 最初に行う基本処理
        super().clean()

        # self.data から画面上の最新の選択を取得
        # 保存前（エラー表示中）でも「持ち帰り」への変更を即座に検知できる
        purchase_type_id = self.data.get('purchase_type')

        # 持ち帰り判定（ID または 文字列で判定）
        is_takeout = (purchase_type_id in ['take_home', '持ち帰り'])

        active_kind_count = 0
        total_qty = 0
        
        prefix = self.prefix

        
        for i, form in enumerate(self.forms):
            # 1. 削除チェック（レ点）が画面で入っているか
            is_delete_checked = self.data.get(f'{prefix}-{i}-DELETE') == 'on'

            should_delete = is_delete_checked or form.cleaned_data.get('DELETE', False)

            if should_delete:
                continue # 削除予定の行は、種類数にも本数にも含めない

            # タイヤと本数の取得
            # ここもcleaned_dataが空になる可能性を考慮し、生のデータも参照
            tire_id = self.data.get(f'{prefix}-{i}-tire')
            qty_raw = self.data.get(f'{prefix}-{i}-quantity') or 0

            try:
                qty = int(qty_raw)
            except (ValueError, TypeError):
                qty = 0

            # タイヤが選択されている有効な行だけをカウント
            if tire_id and tire_id != '':
                active_kind_count += 1
                total_qty += qty

        # エラー判定（「持ち帰り」でない場合のみ実行）
        if not is_takeout:

            # 種類の制限チェック（前後サイズ違いなど想定、2種類まで）
            if active_kind_count > 2:
                raise forms.ValidationError(
                f"【台数制限エラー】現在{active_kind_count}サイズ選択中です。交換作業ご希望の場合は、1台分(前後サイズ違いのお車など、最大2サイズ選択可能)までにしてください。"
                )

            # 本数の制限チェック（最大8本まで）
            if total_qty > 8:
                raise forms.ValidationError(
                f"【本数制限エラー】現在{total_qty}本選択中です。交換作業ご希望の場合は、最大8本までにしてください。"
                )
            #5本購入(ジムニーなどスペアタイヤとして1本余分に購入)が前提の場合も考慮




# 親(見積)画面の中に、子(見積詳細)を見積画面下方に「表形式(Inline)」で並べる
class EstimateItemInline(admin.TabularInline):
    model = EstimateItem
    formset = EstimateItemInlineFormSet  # ← ここで自作のFormSetを指定！
    # 見積明細の入力フォームで、在庫数や在庫状況をリアルタイムに表示するためのカスタムメソッドを定義
    fields = ('tire', 'quantity', 'unit_price', 'set_price', 'subtotal', 'stock_status_display') 
    # 小計と在庫状況は見積入力の際に自動計算される項目で、誤入力を防ぐために readonly に設定
    readonly_fields = ('unit_price', 'set_price', 'subtotal', 'stock_status_display')
    extra = 2 # 前後サイズ違いの車両を考慮して空行を2行追加
    min_num = 1 # 空見積防止のため、最低1行は必須とする
    can_delete = True

    # 在庫状況をリアルタイムに表示するカスタムメソッド
    def stock_status_display(self, obj):
        if not obj.pk: return "-"
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
    pass


class EstimateChargeInline(admin.TabularInline):
    model = EstimateCharge
    extra = 0
    fields = ('charge_master', 'unit_price', 'quantity_display', 'is_manual_edited')
    readonly_fields = ('quantity_display', 'subtotal')

    def quantity_display(self, obj):
        if not obj.id: return "-"
        
        # 手動編集されていたら青太字で表示
        if obj.is_manual_edited:
            return format_html('<b style="color: blue; border-bottom: 1px solid blue;">{} (手動修正済み)</b>', obj.quantity)
        
        return obj.quantity
    
    quantity_display.short_description = "数量"

    # JavaScriptで「数量が変わったらチェックを入れる」
    class Media:
        js = ('js/admin_estimate_custom.js',)


# 見積入力画面（EstimateItem を Inline で入力可能にする）
@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
    # 画面から入力を消して、自動セットにする項目を exclude に追加
    exclude = ('created_by', 'updated_by')
    # 管理画面の一覧表にどの項目を表示するか指定
    list_display = ('estimate_number', 'customer_name', 'vehicle_name', 'colored_status', 'total_price', 'created_at','get_created_at_jst', 'is_fixed')
    # 合計金額や作成日時を画面上で勝手に書き換えられないよう保護
    readonly_fields = ('estimate_number', 'total_price', 'created_at', 'updated_at', 'is_fixed')
    # フォームのレイアウトをカスタマイズ（フィールドセットを定義して、関連する項目をグループ化）fields は 1つにまとめる
    fields = ('customer_name', 'vehicle_name', 'purchase_type', 'estimate_status', 'is_fixed', 'total_price', 'updated_at', 'created_at')
    # 表形式の子テーブルを見積の編集画面にドッキング
    inlines = [EstimateItemInline, EstimateChargeInline]
    # 画面上部に検索バー、画面右側に日付フィルター追加
    search_fields = ('estimate_number', 'customer_name', 'vehicle_name') # 見積番号と顧客名・車種で検索可能
    list_filter = ('created_at', 'purchase_type') # 作成日時と購入タイプで絞り込み可能

    class Media:
        js = ('js/admin_estimate_custom.js',) # static/js/ 以下のパスを指定

    def get_readonly_fields(self, request, obj=None):
        
        # 確定ステータスの見積は、全フィールドを読み取り専用にする
        base_readonly = list(super().get_readonly_fields(request, obj))

        # 提供されたコードに合わせて obj.estimate_status.is_fixed で判定
        if obj and obj.estimate_status and obj.estimate_status.is_fixed:
            all_fields = [f.name for f in self.model._meta.fields]
            # 重複を排除しつつ全フィールドをロック
            return list(set(base_readonly + all_fields))

        return base_readonly

    def has_change_permission(self, request, obj=None):
        # 確定済みの場合は編集権限（保存ボタン）を消す
        if obj and obj.estimate_status and obj.estimate_status.is_fixed:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # 確定済みの場合は削除権限を消す
        if obj and obj.estimate_status and obj.estimate_status.is_fixed:
            return False
        return super().has_delete_permission(request, obj)


    # 新規作成画面を開いた瞬間、見積ステータスの初期値を「作成中」にセットするためのオーバーライド
    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        try:
            initial['estimate_status'] = EstimateStatus.objects.get(status_name="作成中")  # デフォルトの 作成中ステータス をセット
        except EstimateStatus.DoesNotExist:
            pass
        return initial
    
    def get_created_at_jst(self, obj):
        # 日本時間に変換して読みやすい形式で返す
        if obj.created_at:
            return timezone.localtime(obj.created_at).strftime('%Y/%m/%d %H:%M')
        return "-"
    get_created_at_jst.short_description = "作成日時"
    

    # 監査ログはシステムが自動で記録するものであるため、管理画面からの編集は一切禁止する方針
    # 本体の保存（作成者・更新者の自動セット）
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user # 新規作成時は作成者をセット
        obj.updated_by = request.user # 更新時は常に更新者をセット

        # 画面（form）から直接、最新の購入タイプを取得して本体(obj)にセット
        # バリデーションエラー中であっても変更を強制的に反映させます
        if 'purchase_type' in form.cleaned_data:
            obj.purchase_type = form.cleaned_data['purchase_type']
        
        super().save_model(request, obj, form, change)


    def save_formset(self, request, form, formset, change):
        # まず formset.save(commit=False) を実行、Djangoが内部で「削除対象」や「修正対象」を整理
        instances = formset.save(commit=False)

        # 削除チェック が入ったものを物理削除
        for obj in formset.deleted_objects:
            obj.delete()

        # 親（見積本体）の情報を取得、status だけを確認
        parent_obj = form.instance
        # hasattrを使って、安全にステータスがあるか確認し、文字列にする
        status_name = str(parent_obj.estimate_status) if parent_obj.estimate_status else ""
        
        is_creating = "作成中" in status_name


        # 残ったタイヤ明細を保存
        for instance in instances:
            # タイヤが選ばれていて、かつステータスが「作成中」なら価格コピー
            if is_creating and hasattr(instance, 'tire') and instance.tire:
                tire_master = instance.tire
                # 1本価格が空ならマスターからコピー
                # 単価のコピー（マスターの unit_price を使用）
                if not instance.unit_price:
                    instance.unit_price = tire_master.unit_price
                # 4本特価が空ならマスターからコピー
                # 4本特価のコピー（マスターの set_price を使用）
                if not instance.set_price:
                    instance.set_price = tire_master.set_price

            # データベースに保存
            instance.save()
        
        # 多対多のリレーションがある場合に備えて実行
        formset.save_m2m()


    # 明細保存後の最終処理（計算とルールチェック）,EstimateItem の Inline 保存後に呼ばれる
    def save_related(self, request, form, formsets, change):
        # まず Inline（タイヤ明細など）をすべて保存
        # 保存が終わった直後に一度だけ計算(これが一番安全でパフォーマンスが良いタイミング)
        super().save_related(request, form, formsets, change)


        estimate = form.instance
        if not estimate.is_fixed:
            # calculator.py から必要な関数をインポート（このタイミングで呼ぶのが安全）
            from estimate.services.calculator import recalc_all
            # 諸費用の同期と合計金額の計算を一気に実行( sync_estimate_charges と recalc_estimate が走る)
            recalc_all(estimate)

        # 3. ルールチェック（車種必須・台数制限など）
        try:
            estimate.full_clean() 
            # validate_estimate_rules が別にある場合はここでも実行
            # validate_estimate_rules(estimate)

        except ValidationError as e:
            error_msg = " ".join(e.messages) if hasattr(e, 'messages') else str(e)
            messages.error(request, f"保存時にエラーが発生しました: {error_msg}")
            # エラーメッセージを画面に表示

            # 【強制引き戻し処理】
            # エラーがあるのにステータスを「予約確定」にして保存しようとした場合
            if estimate.estimate_status.status_name == "予約確定":
                draft_status = EstimateStatus.objects.filter(status_name="作成中").first()
                if draft_status:
                    estimate.estimate_status = draft_status
                    estimate.save(update_fields=['estimate_status'] ) # ステータスを「作成中」に書き換えて保存
                    messages.warning(request, "⚠️重大なエラーがあるため、ステータスを自動的に「作成中」に戻しました。内容を修正してください。")


    # 見積の状態に応じてステータスを色分けして表示するカスタムメソッド
    def colored_status(self, obj):
        status = obj.estimate_status
        # 万が一ステータスが設定されていない場合の安全策
        if not status: return "—"
        # ステータスの is_fixed によって色分け（例：確定ステータスは赤、未確定ステータスはオレンジ）
        if status.is_fixed:
            return format_html('<span style="color:white; background-color:#d9534f; padding:2px 6px; border-radius:4px;">{}</span>', status.status_name)
        return format_html('<span style="color:#333; background-color:#f0ad4e; padding:2px 6px; border-radius:4px;">{}</span>', status.status_name)
    colored_status.short_description = 'ステータス' # 管理画面の列見出し


@admin.register(EstimateStatus)
class EstimateStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'status_name', 'is_fixed')

# タイヤの状態(廃盤・取扱停止)を管理するための外部キーをリスト表示に追加
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    readonly_fields = [f.name for f in AuditLog._meta.fields]  # すべてのフィールドを読み取り専用に設定
    def has_add_permission(self, request): return False # 管理画面上での追加・変更・削除をすべて禁止
    def has_change_permission(self, request, obj=None): return False # 管理画面上での変更・削除をすべて禁止
    def has_delete_permission(self, request, obj=None): return False # 管理画面上での削除をすべて禁止

# 一番下あたりに追加
@admin.register(ChargeMaster)
class ChargeMasterAdmin(admin.ModelAdmin):
    # 管理画面の一覧で見たい項目
    list_display = ('code', 'name', 'unit_price')
    # 検索ボックスで探せる項目
    search_fields = ('code', 'name')