import json
from django.views.generic import ListView, CreateView, DetailView
from django.forms import inlineformset_factory
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib.auth import get_user_model

from inventory.models import Tire
from ..models import Estimate, EstimateItem, EstimateStatus
from ..forms import EstimateTireForm
from ..services.usecase import EstimateUseCase

# ユーザーモデルを取得
User = get_user_model()

# ==========================================
# 1. フォームセットの設定
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