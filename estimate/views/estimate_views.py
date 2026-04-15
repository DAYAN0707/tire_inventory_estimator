import json # タイヤマスタの価格情報をJSに渡すために使用
from django.views.generic import ListView, CreateView, DetailView, UpdateView, TemplateView # クラスベースView用
from django.forms import inlineformset_factory # フォームセット用
from django.urls import reverse, reverse_lazy
from django.shortcuts import redirect, get_object_or_404, render # リダイレクトとオブジェクト取得用

from django.contrib import messages  # 通知用
from django.contrib.auth import get_user_model  # ユーザーモデル用


from inventory.models import Tire # タイヤマスタの情報を取得するためにインポート
from estimate.forms import EstimateTireForm # タイヤ明細用のフォーム
from estimate.services.usecase import EstimateUseCase # ビジネスロジックを担うUseCaseクラス
from estimate.models import Estimate, EstimateItem, EstimateStatus, ChargeMaster  # 見積関連のモデルをインポート
from estimate.services.calculator import sync_estimate_charges # 諸費用計算サービスをインポート


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

#==========================================
# 4. APIで呼び出すための関数ベースView（add_item）
#========================================== 
# 画面上の「タイヤ追加」ボタンからPOSTリクエストで呼び出される
def add_item(request, tire_id):
    if request.method == "POST":
        User = get_user_model() # ユーザーモデルを取得
        
        # 🎯 フォームの hidden input から見積IDを取得
        estimate_id = request.POST.get("estimate_id")

        # 1. 見積オブジェクトを特定または新規作成
        if estimate_id and estimate_id != "None" and estimate_id != "":
            # 既存の見積に追加する場合
            estimate = get_object_or_404(Estimate, id=estimate_id)
        else:
            # --- 🎯 開発用の安全ユーザー取得 ---
            current_user = User.objects.first() 
            
            if not current_user:
                messages.error(request, "管理画面からユーザーを1人以上作成してください。")
                return redirect('inventory:tire_list')

            # --- 🎯 新規見積を作成 ---
            # 開発中は確実に諸費用（工賃等）が計算されるよう 'install' (店舗付け) を指定
            estimate = Estimate.objects.create(
                customer_name="新規顧客",
                created_by=current_user,
                purchase_type="install"  # 👈 ここで工賃計算のフラグを立てる！
            )
        
        # 2. 追加するタイヤを取得
        tire = get_object_or_404(Tire, id=tire_id)
        
        # 3. フォームから数量と装着位置を取得
        try:
            qty = int(request.POST.get("quantity", 4))
        except (ValueError, TypeError):
            qty = 4
        
        pos = request.POST.get("position", "all")

        # 🎯 工賃マスタの存在チェック（最低1件必要）
        master = ChargeMaster.objects.first()
        if not master:
            messages.error(request, "諸費用マスタが登録されていません。管理画面から登録してください。")
            return redirect('inventory:tire_list')

        # 4. 見積明細（EstimateItem）を作成または更新
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
            item.save()

        # 🎯 諸費用の自動生成と合計金額の反映
        # ① タイヤ構成に合わせて「廃タイヤ」「バルブ」などを自動生成
        sync_estimate_charges(estimate)
        
        # ② 生成された諸費用も含めて、見積全体の最終合計金額を算出
        estimate.recalc_total_price()


        # 5. 完成した見積の詳細画面へ
        #詳細画面ではなく、作成画面(create)へIDを持って戻る ---
        # 'estimate:estimate_create' とすることで、app_name='estimate' 内の 'estimate_create' を探す
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
# 5. ステータス更新専用View（従業員操作用）
# ==========================================
def update_status(request, pk):
    """
    見積詳細画面から従業員がステータス（予約確定・引渡完了など）を直接変更するための処理
    """
    if request.method == "POST":
        estimate = get_object_or_404(Estimate, pk=pk)
        
        quick_status_name = request.POST.get('quick_status')
        status_id = request.POST.get('status_id')

        try:
            if quick_status_name:
                new_status = EstimateStatus.objects.get(status_name=quick_status_name)
            elif status_id:
                new_status = EstimateStatus.objects.get(id=status_id)
            else:
                return redirect('estimate:estimate_detail', pk=pk)

            estimate.estimate_status = new_status
            estimate.save()
            
            messages.success(request, f"ステータスを「{new_status.status_name}」に更新しました。")

        except EstimateStatus.DoesNotExist:
            messages.error(request, "指定されたステータスがマスタに登録されていません。")
        except Exception as e:
            messages.error(request, f"予期せぬエラーが発生しました: {str(e)}")

    return redirect('estimate:estimate_detail', pk=pk)


# ==========================================
# 6. 店長用：マスタ・在庫管理View
# ==========================================

class ManagerTireListView(ListView):
    """タイヤ在庫一覧（店長用）"""
    model = Tire
    template_name = 'estimate/manager_tire_list.html'
    context_object_name = 'tires'

class ManagerTireUpdateView(UpdateView):
    """タイヤ情報編集（店長用）"""
    model = Tire
    fields = ['product_code', 'unit_price', 'set_price', 'reorder_point', 'cost_price', 'stock_qty', 'is_runflat']
    template_name = 'estimate/manager_tire_form.html'
    success_url = reverse_lazy('estimate:manager_tire_list')

class ManagerChargeListView(ListView):
    """諸費用マスタ一覧（店長用）"""
    model = ChargeMaster
    template_name = 'estimate/manager_charge_list.html'
    context_object_name = 'charges'

class ManagerChargeUpdateView(UpdateView):
    """諸費用マスタ編集・削除（店長用）"""
    model = ChargeMaster
    fields = CHARGE_FIELDS
    template_name = 'estimate/manager_charge_form.html'
    success_url = reverse_lazy('estimate:manager_charge_list')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if 'delete' in request.POST:
            self.object.delete()
            messages.success(request, f"「{self.object.name}」を削除しました。")
            return redirect(self.success_url)

        form = self.get_form()
        if form.is_valid():
            charge = form.save(commit=False)
            charge.is_active = 'is_active' in request.POST
            charge.per_tire = 'per_tire' in request.POST
            charge.requires_rft = 'requires_rft' in request.POST
            charge.save()
            messages.success(request, f"「{charge.name}」を更新しました。")
            return redirect(self.success_url)

        return self.form_invalid(form)

class ManagerChargeCreateView(CreateView):
    """諸費用マスタ新規登録（店長用）"""
    model = ChargeMaster
    fields = CHARGE_FIELDS
    template_name = 'estimate/manager_charge_form.html'
    success_url = reverse_lazy('estimate:manager_charge_list')


# ==========================================
# 7. 特殊操作：データクリーンアップ
# ==========================================

def clean_draft_estimates(request):
    """
    【店長権限専用】作成中データを一括清掃
    """
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
    fields = '__all__'
    template_name = 'estimate/manager_status_form.html'
    success_url = reverse_lazy('estimate:status_list')

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
    success_url = reverse_lazy('estimate:status_list')

    def form_valid(self, form):
        # 🎯 内部名 is_fixed に統一
        if 'is_fixed' not in self.request.POST:
            form.instance.is_fixed = False
        else:
            form.instance.is_fixed = True
            
        messages.success(self.request, f"ステータス「{form.instance.status_name}」を登録しました。")
        return super().form_valid(form)
    

class ManagerDashboardView(TemplateView):
    template_name = 'estimate/manager_dashboard.html'