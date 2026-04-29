import json # タイヤマスタの価格情報をJSに渡すために使用
from django.views.generic import ListView, CreateView, DetailView, UpdateView, TemplateView # クラスベースView用
from django.forms import inlineformset_factory # フォームセット用
from django.urls import reverse, reverse_lazy
from django.shortcuts import redirect, get_object_or_404, render # リダイレクトとオブジェクト取得用
from django.db import transaction # トランザクション管理用
from django.contrib import messages  # 通知用
from django.contrib.auth import get_user_model  # ユーザーモデル用
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin # ログイン必須・権限判定用
from inventory.models import Tire # タイヤマスタの情報を取得するためにインポート
from estimate.forms import EstimateTireForm # タイヤ明細用のフォーム
from estimate.services.usecase import EstimateUseCase # ビジネスロジックを担うUseCaseクラス 
from estimate.models import Estimate, ChargeMaster, EstimateStatus # 見積関連のモデルをインポート
from estimate.models.estimate_item import EstimateItem
from estimate.services.calculator import sync_estimate_charges # 諸費用計算サービスをインポート
from audit.utils import write_audit_log # 監査ログ記録用のユーティリティ関数をインポート

# ユーザーモデルを取得
User = get_user_model()

# ==========================================
# 1. 補助関数の設定（在庫ステータス連動メッセージ）
# ==========================================
def get_delivery_message(estimate):
    """
    admin.pyの在庫管理ルールと完全に同期したメッセージ判定。
    1. 在庫あり (stock_qty > 0)
    2. 取り寄せ (reorder_point が 0 または None) ※キャンセル不可
    3. 入荷待ち (上記以外 = 常備在庫だが欠品中)
    """
    # 見積に紐づく最初のタイヤを取得（複数ある場合は最初の1本を基準に判定）
    first_item = estimate.items.first()
    
    if not first_item or not first_item.tire:
        return "在庫状況・納期については、店舗までお問い合わせください。"

    tire = first_item.tire
    main_message = ""

    # --- admin.py の stock_status と同じロジックで分岐 ---
    
    # ① 在庫あり (obj.stock_qty > 0)
    if tire.stock_qty > 0:
        main_message = "現在、こちらの商品は店舗に在庫がございます。即日のお渡しが可能でございます。"
    
    # ② 取り寄せ (obj.reorder_point in (None, 0))
    elif tire.reorder_point in (None, 0):
        main_message = (
            "こちらの商品はお取り寄せとなります。納期については、受け取りご希望の店舗までお問い合わせください。"
            "<br><b>また、取り寄せ商品の性質上、ご注文後のキャンセル・返金は一切お受けできません。</b>"
        )
    
    # ③ 入荷待ち (それ以外：在庫0かつ発注点あり)
    else:
        main_message = "現在、こちらの商品は入荷待ちです。納期については、店舗までお問い合わせください。"

    # 全パターン共通の赤文字フッター
    warning_footer = (
        '<br><span style="color: #dc3545; font-weight: bold;">'
        '※在庫状況は常に変動いたします。お早めのご検討をお願いいたします。'
        '</span>'
    )
    
    return main_message + warning_footer

# ==========================================
# 2. フォームセットの設定
# ==========================================
EstimateTireFormSet = inlineformset_factory(
    Estimate,       # 親モデル
    EstimateItem,   # 子モデル
    form=EstimateTireForm, 
    extra=1,        
    can_delete=True # 🎯 重要：JS側の削除ボタンと連動するために必須
)

class EstimateListView(ListView):
    """見積の一覧を表示するView"""
    model = Estimate
    template_name = 'estimate/estimate_list.html'
    context_object_name = 'estimates'
    ordering = ['-created_at']

class EstimateCreateView(CreateView):
    """
    見積を新規作成し、タイヤ明細（Formset）を同時に管理するView
    在庫一覧からの「追加」による復元ロジックと、手入力の両方に対応
    """
    model = Estimate
    template_name = "estimate/estimate_form.html"
    fields = ["purchase_type", "customer_name", "vehicle_name"]

    def get_success_url(self):
        """保存成功後のリダイレクト先（詳細画面）"""
        return reverse('estimate:estimate_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        """
        画面表示に必要なデータを準備する
        特に『在庫から追加』された場合のデータ復元用JSON作成が重要
        """
        context = super().get_context_data(**kwargs)
        
        # 1. URLパラメータから 'estimate_id' を取得（在庫一覧からの遷移時に付与される）
        estimate_id = self.request.GET.get('estimate_id')
        
        # JSに渡すための初期データ構造
        estimate_data = {"items": []}
        estimate_obj = None

        # --- 🎯 在庫連動時のデータ復元ロジック ---
        if estimate_id:
            try:
                # 関連するアイテム（タイヤ）と諸費用を効率的に取得
                estimate_obj = Estimate.objects.prefetch_related('items__tire').get(id=estimate_id)
                
                # 取得したアイテムをループして、JavaScriptが処理しやすいリスト形式に変換
                for item in estimate_obj.items.all():
                    # 💡 安全策: フィールド名が 'name' か 'product_name' か不明な場合でも
                    # getattr を使うことで AttributeError によるクラッシュを防ぐ
                    t_brand = getattr(item.tire, 'brand', '')
                    t_name = getattr(item.tire, 'name', getattr(item.tire, 'product_name', ''))
                    t_size = getattr(item.tire, 'size', '')

                    estimate_data["items"].append({
                        "tire_id": item.tire.id,
                        "tire_name": f"{t_brand} {t_name} {t_size}".strip(),
                        "quantity": item.quantity,
                        "unit_price": float(item.unit_price or 0),
                        "subtotal": float(item.subtotal or 0),
                    })
            except Estimate.DoesNotExist:
                # IDが不正な場合は無視して新規作成として扱う
                pass

        # 2. テンプレートへ渡す変数をセット
        context['estimate'] = estimate_obj
        # 💡 これがテンプレートの <script id="estimate-data"> 内で {{ estimate_json|safe }} として使われる
        context['estimate_json'] = json.dumps(estimate_data)

        # --- 🎯 Formset（タイヤ入力行）の動的制御 ---
        if self.request.POST:
            # 保存ボタン押下時（バリデーションNGで戻ってきた場合など）
            context['tire_formset'] = EstimateTireFormSet(self.request.POST)
        else:
            # 画面表示時：復元するタイヤの数に合わせて初期行数（extra）を調整
            # 1つもデータがなければ1行、あればその数だけ「入力箱」を作る
            initial_count = len(estimate_data["items"]) if estimate_id else 1
            
            # extraを動的に変更したフォームセットをその場で生成
            DynamicFormSet = inlineformset_factory(
                Estimate, EstimateItem, 
                form=EstimateTireForm, # 定義済みのフォームを使用
                extra=max(1, initial_count), # 最低1行は確保
                can_delete=True
            )
            context['tire_formset'] = DynamicFormSet()

        # --- 🎯 3. 【最重要】計算用のタイヤマスタデータを追加 ---
        tires_queryset = Tire.objects.all().values(
            "id",
            "unit_price",
            "set_price",
            "is_runflat",
        )

        context["tires_json"] = json.dumps(list(tires_queryset), default=str)

        return context


# --- [保存ボタンが押された時の処理] ---
    def form_valid(self, form):
        context = self.get_context_data()
        tire_formset = context['tire_formset']
        purchase_type = form.cleaned_data.get('purchase_type')

        # 1. タイヤ明細の入力チェック
        if tire_formset.is_valid():
            try:
                # バリデーション：削除・数量0を除外してカウント
                valid_items_count = 0
                for tire_form in tire_formset:
                    if tire_form.cleaned_data.get('DELETE') or tire_form.cleaned_data.get('quantity', 0) == 0:
                        continue
                    valid_items_count += 1

                # 台数制限チェック
                if purchase_type == 'exchange' and valid_items_count > 2:
                    form.add_error(None, "【台数制限】交換作業ありの場合、タイヤは2種類までです。")
                    return self.render_to_response(self.get_context_data(form=form))

                # --- 基本情報の準備 ---
                estimate = form.save(commit=False)
                
                # 作成者セット
                if self.request.user.is_authenticated:
                    estimate.created_by = self.request.user
                else:
                    first_user = User.objects.first()
                    if not first_user:
                        form.add_error(None, "ユーザーが登録されていないため保存できません。")
                        return self.render_to_response(self.get_context_data(form=form))
                    estimate.created_by = first_user

                # --- 🎯 修正：保存時のステータスを最初から「見積確定」にする ---
                # お客様が「保存」した時点で作成フローは完了しているため、
                # 内部的な「作成中」ではなく、従業員がすぐに追える「見積確定」をセットしておく
                try:
                    status_confirmed = EstimateStatus.objects.get(status_name='見積確定')
                    estimate.estimate_status = status_confirmed
                except EstimateStatus.DoesNotExist:
                    form.add_error(None, "マスタに '見積確定' というステータスが必要です。")
                    return self.render_to_response(self.get_context_data(form=form))
                
                # --- 手入力された諸費用データの収集 ---
                manual_dict = {}
                for key, val in self.request.POST.items():
                    if key.startswith("charge_qtys["):
                        manual_key = key.replace("charge_qtys[", "").replace("]", "")
                        if val is not None and val != "":
                            try:
                                manual_dict[manual_key] = int(val)
                            except ValueError:
                                continue

                # --- UseCaseの呼び出し ---
                self.object = EstimateUseCase.create_estimate(
                    estimate_instance=estimate,
                    tire_formset=tire_formset,
                    user=estimate.created_by,
                    manual_data=manual_dict
                )
                # 新規作成（見積確定）のログ
                write_audit_log(
                    request=self.request,
                    target_type='estimate',
                    target_id=self.object.id,
                    action='status_change', # 初期作成
                    before=None,
                    after={'status': '見積確定'},
                    note="見積を新規作成しました"
                )
                
                return redirect(self.get_success_url())

            except Exception as e:
                form.add_error(None, f"システムエラーが発生しました: {str(e)}")
                return self.render_to_response(self.get_context_data(form=form))
        else:
            return self.render_to_response(self.get_context_data(form=form))

class EstimateDetailView(DetailView):
    """作成された見積の最終結果を確認し、従業員がステータスを管理するView"""
    model = Estimate
    template_name = 'estimate/estimate_detail.html'
    context_object_name = 'estimate'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['delivery_message'] = get_delivery_message(self.object)
        # 🎯 従業員がプルダウンで選べるように、全ステータスをテンプレートに送る
        context['statuses'] = EstimateStatus.objects.all()
        return context

    def post(self, request, *args, **kwargs):
        """詳細画面（管理画面）からのステータス更新を受け付ける"""
        if not request.user.is_authenticated:
            return redirect('login')

        estimate = self.get_object()
        new_status_id = request.POST.get('status_id')

        if new_status_id:
            try:
                new_status = EstimateStatus.objects.get(id=new_status_id)
                estimate.estimate_status = new_status
                estimate.save()
            except EstimateStatus.DoesNotExist:
                pass
        
        return redirect('estimate:estimate_detail', pk=estimate.pk)

# ==========================================
# 3. 印刷専用Viewの追加
# ==========================================
def estimate_print(request, pk):
    """
    【新規追加】印刷専用ページを表示する関数ベースView。
    A4印刷に最適化されたテンプレート（estimate_print.html）を返します。
    """
    estimate = get_object_or_404(Estimate, pk=pk)
    
    context = {
        "estimate": estimate,
        "items": estimate.items.all(),
        "charges": estimate.charges.all(),
        "delivery_message": get_delivery_message(estimate), # 納期案内
    }
    return render(request, "estimate/estimate_print.html", context)

# ==========================================
# 4. APIで呼び出すための関数ベースView（add_item）
# ========================================== 
# 画面上の「タイヤ追加」ボタンからPOSTリクエストで呼び出される
def add_item(request, tire_id):
    if request.method != "POST":
        return redirect('inventory:tire_list')

    User = get_user_model()
    current_user = User.objects.first()

    # --- 🎯 開発用の安全ユーザー取得 ---
    if not current_user:
        messages.error(request, "管理画面からユーザーを1人以上作成してください。")
        return redirect('inventory:tire_list')

    # 🎯 フォームの hidden input から見積IDを取得
    estimate_id = request.POST.get("estimate_id")

    # ==========================================
    # 🔍 デバッグログ
    # ==========================================
    print("==== DEBUG START ====")
    print("tire_id:", tire_id)
    print("tire exists:", Tire.objects.filter(id=tire_id).exists())
    print("estimate_id:", estimate_id if estimate_id else "なし")
    
    # ステータスマスタの状態を確認
    try:
        print("statuses in DB:", list(EstimateStatus.objects.values('id', 'status_name')))
    except Exception as e:
        print("Status Debug Error:", e)
    print("==== DEBUG END ====")
    # ==========================================

    # 🎯 ステータスマスタの取得
    default_status = EstimateStatus.objects.first()

    if not default_status:
        messages.error(request, "ステータスマスタが空です。管理画面から登録してください。")
        return redirect('estimate:status_list')

    # ① 見積オブジェクトを特定または新規作成
    if estimate_id and estimate_id != "None" and estimate_id != "":
        # 既存の見積に追加する場合
        estimate = get_object_or_404(Estimate, id=estimate_id)
    else:
        # --- 🎯 新規見積を作成 ---
        # IntegrityError回避のため、上で取得した default_status を明示的にセット
        estimate = Estimate.objects.create(
            customer_name="新規顧客",
            created_by=current_user,
            purchase_type="install", 
            estimate_status=default_status 
        )

    # ② 追加するタイヤを取得
    tire = get_object_or_404(Tire, id=tire_id)

    # ③ フォームから数量と装着位置を取得
    try:
        qty = int(request.POST.get("quantity", 4))
    except (ValueError, TypeError):
        qty = 4

    pos = request.POST.get("position", "all")

    # 🎯 工賃マスタの存在チェック
    master = ChargeMaster.objects.first()
    if not master:
        messages.error(request, "諸費用マスタが登録されていません。")
        return redirect('inventory:tire_list')

    # ④ 見積明細（EstimateItem）を作成または更新
    # 🌟 estimate_item.py で定義されたロジックに基づき保存
    item, created = EstimateItem.objects.get_or_create(
        estimate=estimate,
        tire=tire,
        position=pos,
        defaults={
            'quantity': qty, 
            'cost_master': master
        }
    )
    
    if not created:
        item.quantity += qty
        item.save() # ここで estimate_item.py の save() メソッドが動く

    # 🎯 合計金額の反映（Estimateモデル側のメソッド）
    if hasattr(estimate, 'recalc_total_price'):
        estimate.recalc_total_price()

    # ⑤ 完成した見積の作成画面(create)へ戻る
    redirect_url = reverse('estimate:estimate_create')
    return redirect(f"{redirect_url}?estimate_id={estimate.id}")

# ==========================================
# 諸費用フォームで使用するフィールド一覧
# ==========================================
CHARGE_FIELDS = [
    'name', 
    'code', 
    'charge_type',
    'unit_price', 
    'min_inch',
    'max_inch',
    'per_tire',
    'requires_rft',
    'is_active'
]

# ==========================================
# 5. ステータス更新専用View（従業員操作用・アクセス制限 ＆ 在庫連動 ＆ 監査ログ対応版）
# ==========================================
class EstimateStatusUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    見積詳細画面から従業員がステータスを変更するための処理
    """
    model = Estimate
    fields = ['estimate_status']

    def dispatch(self, request, *args, **kwargs):
        # デモグループの早期ガード
        if request.user.groups.filter(name="demo_group").exists():
            messages.warning(request, "デモアカウントでは見積ステータスの編集・登録は制限されています。")
            pk = self.kwargs.get('pk')
            return redirect('estimate:estimate_detail', pk=pk) if pk else redirect('estimate:estimate_list')
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        return self.request.user.is_staff

    def handle_no_permission(self):
        messages.error(self.request, "この操作には従業員権限が必要です。")
        pk = self.kwargs.get('pk')
        return redirect('estimate:estimate_detail', pk=pk) if pk else redirect('estimate:estimate_list')

    def post(self, request, *args, **kwargs):
        """詳細画面（管理画面）からのステータス更新を受け付ける"""
        # 🚀 ログ出力（RenderのログでView到達を確認するため）
        print("DEBUG POST HIT")
        
        # 🛡️ 1. URLからpkを安全に取得し、存在チェック
        pk = self.kwargs.get('pk')
        if not pk:
            messages.error(request, "不正なリクエストです（見積IDが見つかりません）")
            return redirect('estimate:estimate_list')

        # 🛡️ 2. filter().first() で安全にデータを取得（DoesNotExistを回避しつつ自前でリダイレクト）
        estimate = Estimate.objects.filter(pk=pk).first()
        if not estimate:
            messages.error(request, "対象の見積データが見つかりませんでした。")
            return redirect('estimate:estimate_list')
        
        quick_status_name = request.POST.get('quick_status')
        status_id = request.POST.get('status_id')
        new_status = None

        try:
            # 🛡️ 3. ステータス取得を「明示的な取得」に変更（サイレント失敗の防止）
            if quick_status_name:
                # get() を使い、存在しない場合はあえて例外(DoesNotExist)を飛ばす
                new_status = EstimateStatus.objects.get(status_name=quick_status_name)
            elif status_id:
                # ID指定の場合も get()。無効なIDなら例外を飛ばしてキャッチする
                new_status = EstimateStatus.objects.get(id=status_id)

            # 何も取得できなかった場合のガード（基本的にここには到達しない）
            if not new_status:
                messages.warning(request, "変更後のステータスが特定できませんでした。")
                return redirect('estimate:estimate_detail', pk=estimate.pk)

            old_status_name = estimate.estimate_status.status_name
            new_status_name = new_status.status_name

            # 🎯 ステータスに変更がある場合のみ在庫処理を実行
            if old_status_name != new_status_name:
                action_code = "status_change" 

                with transaction.atomic():
                    # 🛡️ 4. None計算エラー(TypeError)の徹底防止策
                    # 全ての tire.field に対して (field or 0) を適用
                    
                    # ① [予約確定] 見積確定 → 予約確定
                    if old_status_name == "見積確定" and new_status_name == "予約確定":
                        action_code = "reserve_confirm"
                        for item in estimate.items.all():
                            tire = item.tire
                            qty = item.quantity or 0
                            # 🛡️ Noneガード: 既存値がNoneなら0として計算
                            tire.reserved_qty = (tire.reserved_qty or 0) + qty
                            tire.save()

                    # ② [予約キャンセル] 予約確定 → 予約キャンセル
                    elif old_status_name == "予約確定" and new_status_name == "予約キャンセル":
                        action_code = "reserve_cancel"
                        for item in estimate.items.all():
                            tire = item.tire
                            qty = item.quantity or 0
                            # 🛡️ Noneガード ＋ マイナス防止
                            tire.reserved_qty = max(0, (tire.reserved_qty or 0) - qty)
                            tire.save()

                    # ③ [引渡完了] 予約確定 → 引渡完了
                    elif old_status_name == "予約確定" and new_status_name == "引渡完了":
                        for item in estimate.items.all():
                            tire = item.tire
                            qty = item.quantity or 0
                            # 🛡️ 実在庫・予約枠ともにNoneガード ＋ マイナス防止
                            tire.stock_qty = max(0, (tire.stock_qty or 0) - qty)
                            tire.reserved_qty = max(0, (tire.reserved_qty or 0) - qty)
                            tire.save()

                    # 見積自身のステータスを更新
                    estimate.estimate_status = new_status
                    estimate.save()

                    # 🌟 監査ログ（原因切り分けのため一時的にコメントアウト。安定後、utilsのインポートを確認して戻す）
                    """
                    write_audit_log(
                        request=request, target_type='estimate', target_id=estimate.id,
                        action=action_code, before={'status': old_status_name},
                        after={'status': new_status_name},
                        note=f"ステータスを {old_status_name} から {new_status_name} へ変更しました。"
                    )
                    """
                
                messages.success(request, f"ステータスを「{new_status.status_name}」に更新しました。")
            else:
                messages.info(request, "ステータスに変更はありませんでした。")

        except EstimateStatus.DoesNotExist:
            # 🛡️ get() でデータが見つからなかった場合の明確なエラー通知
            messages.error(request, f"エラー：マスタに指定のステータスが存在しません。")
        except Exception as e:
            # 🛡️ TypeError や DBエラーなど、すべての予期せぬエラーをここでキャッチして500を回避
            messages.error(request, f"システムエラーが発生しました: {str(e)}")

        return redirect('estimate:estimate_detail', pk=estimate.pk)

# ==========================================
# 6. 店長用：マスタ・在庫管理View
# ==========================================

class ManagerTireListView(ListView):
    """タイヤ在庫一覧（店長用）"""
    model = Tire
    template_name = 'estimate/manager_tire_list.html'
    context_object_name = 'tires'
    
class ManagerTireUpdateView(LoginRequiredMixin, UpdateView):
    """タイヤ情報編集（店長用）"""
    model = Tire
    fields = ['product_code', 'unit_price', 'set_price', 'reorder_point', 'cost_price', 'stock_qty', 'is_runflat']
    template_name = 'estimate/manager_tire_form.html'
    success_url = reverse_lazy('estimate:manager_tire_list')
    
    def dispatch(self, request, *args, **kwargs):
        # 🎯 ここで全てのアクセス（表示も保存も）をシャットアウト
        if request.user.groups.filter(name="demo_group").exists():
            messages.warning(
                request, 
                "デモアカウントではタイヤマスタの編集は制限されています。"
            )
            return redirect('estimate:manager_tire_list')
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        #  dispatchで弾いている為、ここには店長（通常ユーザー）しか来ない
        self.object = self.get_object()
        form = self.get_form()
        
        if form.is_valid():
            tire = form.save()
            messages.success(request, f"商品コード「{tire.product_code}」の情報を更新しました。")
            return redirect(self.success_url)

        return self.form_invalid(form)

class ManagerChargeListView(ListView):
    """諸費用マスタ一覧（店長用）"""
    model = ChargeMaster
    template_name = 'estimate/manager_charge_list.html'
    context_object_name = 'charges'

class ManagerChargeUpdateView(LoginRequiredMixin, UpdateView):
    """
    諸費用マスタ編集・削除（店長用）
    ■ 役割
    ・諸費用マスタ（工賃など）の編集／削除を行う
    ・デモユーザーは「閲覧も操作も不可」にする（完全ブロック）
    ■ セキュリティ方針
    ① dispatchで全リクエストをブロック（最重要）
    ② postでも念のため再チェック（二重ガード）
    """
    model = ChargeMaster
    fields = CHARGE_FIELDS
    template_name = 'estimate/manager_charge_form.html'
    success_url = reverse_lazy('estimate:manager_charge_list')

    def dispatch(self, request, *args, **kwargs):
        # 🎯 【最重要】デモグループのユーザーを完全ブロック
        if request.user.groups.filter(name="demo_group").exists():
            messages.warning(
                request, 
                "デモアカウントでは諸費用マスタの編集・削除は制限されています。"
            )
            return redirect('estimate:manager_charge_list') # 諸費用一覧へ
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # テンプレート用の追加データを準備
        context = super().get_context_data(**kwargs)
        context['is_demo_user'] = self.request.user.groups.filter(name="demo_group").exists()
        return context

    def post(self, request, *args, **kwargs):
        # 編集対象のオブジェクト取得
        self.object = self.get_object()
        # 【保険】万が一dispatchをすり抜けた場合のガード
        if request.user.groups.filter(name="demo_group").exists():
            messages.error(request, "デモアカウントでは操作できません。")
            return redirect('estimate:manager_charge_list')
        
        # 削除処理
        if 'delete' in request.POST:
            # 💡 将来的には紐づきチェックを入れますが、
            # 現状は Model の構成に合わせて、確実に動く「物理削除」のみを行います。
            self.object.delete()
            messages.success(
                request,
                f"「{self.object.name}」を完全に削除しました。"
            )
            return redirect(self.success_url)

        # 更新処理
        form = self.get_form()
        if form.is_valid():
            charge = form.save(commit=False)
            # チェックボックス系はPOSTに存在するかで判定
            charge.is_active = 'is_active' in request.POST
            charge.per_tire = 'per_tire' in request.POST
            charge.requires_rft = 'requires_rft' in request.POST
            charge.save()
            messages.success(
                request,
                f"「{charge.name}」を更新しました。"
            )
            return redirect(self.success_url)
        # バリデーションエラー時はフォーム再表示
        return self.form_invalid(form)

class ManagerChargeCreateView(CreateView):
    """諸費用マスタ新規登録（店長用）"""
    model = ChargeMaster
    fields = CHARGE_FIELDS
    template_name = 'estimate/manager_charge_form.html'
    success_url = reverse_lazy('estimate:manager_charge_list')
    
# --- 諸費用マスタの有効化処理 ---
def charge_master_activate(request, pk):
    """無効化された諸費用を再度有効にする（関数ベースView）"""
    # 諸費用データを取得（存在しない場合は404エラー）
    charge = get_object_or_404(ChargeMaster, pk=pk)
    
    # 有効フラグをTrueに戻して保存
    charge.is_active = True
    charge.save()
    
    # ユーザーに通知を表示
    messages.success(request, f"「{charge.name}」を再度有効にしました。見積作成時に選択できるようになります。")
    
    # 一覧画面へ戻る
    return redirect('estimate:manager_charge_list')


# ==========================================
# 7. 特殊操作：データクリーンアップ
# ==========================================

def clean_draft_estimates(request):
    """
    【店長権限専用】作成中データを一括清掃
    """
    # 🎯 【セキュリティ追加】デモグループに属するユーザーの一括削除をブロック
    if request.user.groups.filter(name="demo_group").exists():
        messages.error(request, "デモアカウントではデータの一括削除は実行できません。")
        return redirect('estimate:manager_dashboard') # もしくは適切な遷移先

    # 一般スタッフ（is_staff=False）も一応ガード
    if not request.user.is_staff:
        messages.error(request, "この操作には店長権限が必要です。")
        return redirect('estimate:estimate_list')
    try:
        draft_status = EstimateStatus.objects.get(status_name="作成中")
        draft_estimates = Estimate.objects.filter(estimate_status=draft_status)
        count = draft_estimates.count()
        
        draft_estimates.delete()
        draft_status.delete()
        
        messages.success(request, f"「作成中」の見積 {count} 件と、ステータスマスタを完全に消去しました。")
        
    except EstimateStatus.DoesNotExist:
        messages.info(request, "「作成中」のステータスは既に整理済みです。")
    except Exception as e:
        messages.error(request, f"クリーンアップ中にエラーが発生しました: {str(e)}")

    return redirect('estimate:estimate_list')

# ==========================================
# 8. ステータスマスタ管理（店長用）
# ==========================================

class ManagerStatusListView(ListView):
    """ステータス一覧"""
    model = EstimateStatus
    template_name = 'estimate/manager_status_list.html'
    context_object_name = 'statuses'

class ManagerStatusUpdateView(UpdateView):
    """ステータス編集"""
    model = EstimateStatus
    fields = ['status_name', 'is_fixed']
    template_name = 'estimate/manager_status_form.html'
    success_url = reverse_lazy('estimate:status_list')

    def dispatch(self, request, *args, **kwargs):
        if request.user.groups.filter(name="demo_group").exists():
            messages.warning(request, "デモアカウントではステータスの編集は制限されています。")
            return redirect('estimate:manager_status_list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # 🎯 内部名 is_fixed に統一
        if 'is_fixed' not in self.request.POST:
            form.instance.is_fixed = False
        else:
            form.instance.is_fixed = True
        
        messages.success(self.request, f"ステータス「{form.instance.status_name}」を更新しました。")
        return super().form_valid(form)

class ManagerStatusCreateView(CreateView):
    """ステータス新規登録"""
    model = EstimateStatus
    fields = '__all__'
    template_name = 'estimate/manager_status_form.html'
    success_url = reverse_lazy('estimate:manager_status_list')
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.groups.filter(name="demo_group").exists():
            messages.warning(request, "デモアカウントではステータスの編集は制限されています。")
            return redirect('estimate:manager_status_list')
        return super().dispatch(request, *args, **kwargs)

    # 新規作成時も、固定フラグの処理を同様に行う
    def form_valid(self, form):
        # 🎯 内部名 is_fixed に統一
        if 'is_fixed' not in self.request.POST:
            form.instance.is_fixed = False
        else:
            form.instance.is_fixed = True
            
        messages.success(self.request, f"ステータス「{form.instance.status_name}」を登録しました。")
        return super().form_valid(form)

class ManagerDashboardView(LoginRequiredMixin, TemplateView):
    """
    店長・スタッフ共用ダッシュボード
    LoginRequiredMixin を追加することで、ログインさえしていれば
    店長(is_staff=True)でも一般スタッフ(is_staff=False)でもアクセス可能
    """
    template_name = 'estimate/manager_dashboard.html'