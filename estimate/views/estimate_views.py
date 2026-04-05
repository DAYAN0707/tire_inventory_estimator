import json # タイヤマスタの価格情報をJSに渡すために使用
from django.views.generic import ListView, CreateView, DetailView # クラスベースView用
from django.forms import inlineformset_factory # フォームセット用
from django.urls import reverse # URLリバース用
from django.shortcuts import redirect, get_object_or_404, render # リダイレクトとオブジェクト取得用


from django.contrib import messages  # 通知用
from django.contrib.auth import get_user_model  # ユーザーモデル用

from inventory.models import Tire # タイヤマスタの情報を取得するためにインポート
from ..forms import EstimateTireForm # タイヤ明細用のフォーム
from ..services.usecase import EstimateUseCase # ビジネスロジックを担うUseCaseクラス
from ..models import Estimate, EstimateItem, EstimateStatus, ChargeMaster  # 見積関連のモデルをインポート


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
    """見積を新規作成するView"""
    model = Estimate
    template_name = "estimate/estimate_form.html"
    fields = ["purchase_type", "customer_name", "vehicle_name"]

    def get_success_url(self):
        return reverse('estimate:estimate_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # タイヤのマスタデータをJSに渡す
        tires_list = list(Tire.objects.values("id", "unit_price", "set_price"))
        context["tires_json"] = json.dumps(tires_list)

        # フォームセットの準備
        if self.request.POST:
            context['tire_formset'] = EstimateTireFormSet(self.request.POST)
        else:
            context['tire_formset'] = EstimateTireFormSet()
        return context

    # --- [保存ボタンが押された時の処理] ---
    def form_valid(self, form):
        context = self.get_context_data()
        tire_formset = context['tire_formset']
        purchase_type = form.cleaned_data.get('purchase_type')

        # 1. タイヤ明細の入力チェック
        if tire_formset.is_valid():
            try:
                # 🎯 修正2 & 3：サーバー側でのバリデーション（削除・数量0の除外と台数制限）
                valid_items_count = 0
                for tire_form in tire_formset:
                    # 削除フラグがON、または数量が0（空欄含む）のデータはカウントしない
                    if tire_form.cleaned_data.get('DELETE') or tire_form.cleaned_data.get('quantity', 0) == 0:
                        continue
                    valid_items_count += 1

                # 交換作業ありの場合のみ、2種類制限をかける（持ち帰りはスルー）
                if purchase_type == 'exchange' and valid_items_count > 2:
                    form.add_error(None, "【台数制限】交換作業ありの場合、タイヤは2種類までです。")
                    return self.render_to_response(self.get_context_data(form=form))

                # --- 基本情報の準備 ---
                estimate = form.save(commit=False)
                
                # 作成者セット（安全策込み）
                if self.request.user.is_authenticated:
                    estimate.created_by = self.request.user
                else:
                    first_user = User.objects.first()
                    if not first_user:
                        form.add_error(None, "ユーザーが登録されていないため保存できません。")
                        return self.render_to_response(self.get_context_data(form=form))
                    estimate.created_by = first_user

                # ステータスセット
                try:
                    status_draft = EstimateStatus.objects.get(status_name='作成中')
                    estimate.estimate_status = status_draft
                except EstimateStatus.DoesNotExist:
                    form.add_error(None, "マスタに '作成中' というステータスが必要です。")
                    return self.render_to_response(self.get_context_data(form=form))
                
                # --- 🎯 修正1：手入力された諸費用データの収集 ---
                # JSのsubmitイベントで作られた hidden input (charge_qtys[...]) をすべて拾う
                manual_dict = {}
                for key, val in self.request.POST.items():
                    if key.startswith("charge_qtys["):
                        # キーの整形: "charge_qtys[4_0]" -> "4_0"
                        manual_key = key.replace("charge_qtys[", "").replace("]", "")
                        # 値が存在する場合のみ整数として格納
                        if val is not None and val != "":
                            try:
                                manual_dict[manual_key] = int(val)
                            except ValueError:
                                continue

                print(f"DEBUG: サーバー受信(手入力諸費用) -> {manual_dict}")

                # --- 3. UseCaseの呼び出し ---
                # 最終的な保存処理。manual_dataに手入力値が渡され、UseCase内で計算結果を上書きします。
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
    """作成された見積の最終結果を確認するView"""
    model = Estimate
    template_name = 'estimate/estimate_detail.html'
    context_object_name = 'estimate'

    def get_context_data(self, **kwargs):
        """詳細画面でも納期メッセージを表示するために追加"""
        context = super().get_context_data(**kwargs)
        context['delivery_message'] = get_delivery_message(self.object)
        return context

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
            # --- 🎯 開発用の超安全ユーザー取得 ---
            # ログイン状態に関わらず、DBに存在する「最初のユーザー」を強制的に取得する
            current_user = User.objects.first() 
            
            # もしユーザーが1人もいなければ、処理を中断して一覧に戻す
            if not current_user:
                messages.error(request, "管理画面からユーザー（superuser）を1人以上作成してください。")
                return redirect('inventory:tire_list')

            # 新規見積を作成
            estimate = Estimate.objects.create(
                customer_name="新規顧客",
                created_by=current_user  # 👈 これで実在するIDが100%入ります
            )
        
        # 2. 追加するタイヤを取得
        tire = get_object_or_404(Tire, id=tire_id)
        
        # 3. フォームから数量と装着位置を取得
        # 数字以外の変な値が入ってきてもエラーにならないよう try-except で囲む
        try:
            qty = int(request.POST.get("quantity", 4))
        except (ValueError, TypeError):
            qty = 4
        
        # 装着位置を取得（all, front, rear）
        pos = request.POST.get("position", "all")

        # 🎯 最後の落とし穴対策：工賃マスタの存在チェック
        # マスタが0件だと、後続の保存処理でFOREIGN KEYエラーになるため事前に防ぐ
        master = ChargeMaster.objects.first()
        if not master:
            messages.error(request, "工賃マスタが存在しません。管理画面またはシェルから登録してください。")
            return redirect('inventory:tire_list')

        # 4. 見積明細（EstimateItem）を作成または更新
        # position も検索条件に含めることで、同じタイヤでも前輪と後輪を別々に保存
        item, created = EstimateItem.objects.get_or_create(
            estimate=estimate,
            tire=tire,
            position=pos, # 👈 モデルに追加した position と連動！
            defaults={
                'quantity': qty, 
                'cost_master': master # 👈 Noneではなく有効なマスタをセット
            }
        )
        
        # すでに同じタイヤ・同じ位置のものがカートにあれば、数量だけ増やす
        if not created:
            item.quantity += qty
            item.save()
            
        # 5. 完成した見積の詳細画面へリダイレクト
        return redirect('estimate:estimate_detail', pk=estimate.id)