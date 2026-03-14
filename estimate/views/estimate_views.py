from django.views.generic import ListView, CreateView, DetailView
from django.forms import inlineformset_factory
from django.urls import reverse
from django.shortcuts import redirect  # HttpResponseRedirectの代わりに使いやすいこちらを使用
from inventory.models import Tire
from ..models import Estimate, EstimateItem, EstimateStatus
# 業務ロジックを担当するUseCaseをインポート
from ..services.usecase import EstimateUseCase
from django import forms
from ..forms import EstimateTireForm
import json


# フォームセットの設定
EstimateTireFormSet = inlineformset_factory(
    Estimate, # 親モデル
    EstimateItem, # 子モデル
    form=EstimateTireForm, # 上で作った目印付きのフォームを指定
    can_delete=False  # 行の削除を許可するかどうか
)

class EstimateListView(ListView):
    model = Estimate
    template_name = 'estimate/estimate_list.html'
    context_object_name = 'estimates'
    ordering = ['-created_at']

# 見積を新規作成する画面のビュー
class EstimateCreateView(CreateView):
    model = Estimate
    template_name = "estimate/estimate_form.html"
    # ユーザーが入力する基本項目
    fields = ["purchase_type", "customer_name", "vehicle_name"]

    # 保存が成功した後に、作成された見積の詳細画面へリダイレクト
    def get_success_url(self):
        return reverse('estimate:estimate_detail', kwargs={'pk': self.object.pk})

    # HTMLテンプレートに渡すデータ（変数）を準備する
    def get_context_data(self, **kwargs):
        # 親クラスから既存のcontext（formsetなど）を取得
        context = super().get_context_data(**kwargs)
        
        tires_list = list(
            Tire.objects.values(
                "id",
                "unit_price", 
                "set_price" 
            )
        )

        # 
        context["tires_json"] = json.dumps(tires_list)

        if self.request.POST:
            context['tire_formset'] = EstimateTireFormSet(self.request.POST)
        else:
            context['tire_formset'] = EstimateTireFormSet()

        return context

    def form_valid(self, form):
        context = self.get_context_data()
        tire_formset = context['tire_formset']

        if tire_formset.is_valid():
            try:
                # 1. 親モデルのインスタンスをメモリ上に作成（まだ保存しない）
                estimate = form.save(commit=False)
                
                # 2. 【修正箇所】文字列の 'draft' ではなく、モデルからインスタンスを取得する
                # データベースにある EstimateStatus の中から status_name= が 'draft' のものを探します
                try:
                    status_draft = EstimateStatus.objects.get(status_name ='作成中')
                    estimate.estimate_status = status_draft
                except EstimateStatus.DoesNotExist:
                    # もし 'draft' がなければエラーとして表示させる
                    form.add_error(None, "ステータスマスタに 'draft' が登録されていません。")
                    return self.render_to_response(self.get_context_data(form=form)) 
                
                # 3. UseCase に渡して、詳細な計算と最終保存をお任せする
                self.object = EstimateUseCase.create_estimate(
                    estimate_instance=estimate,
                    tire_formset=tire_formset,
                    user=self.request.user
                )
                
                return redirect(self.get_success_url())

            except Exception as e:
                # ここで自作メッセージを含め、エラー内容を表示
                form.add_error(None, str(e))
                return self.render_to_response(self.get_context_data(form=form))
        else:
            return self.render_to_response(self.get_context_data(form=form))
        
# 作成された見積の最終結果を表示する画面
class EstimateDetailView(DetailView):
    model = Estimate
    template_name = 'estimate/estimate_detail.html'
    context_object_name = 'estimate'