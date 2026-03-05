from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView
from django.contrib import messages
from django.db import transaction
from ..models import Estimate
from ..services.calculator import recalc_all

class EstimateCreateView(CreateView):
    """
    見積の基本情報（顧客名、販売形態など）を新規登録するビュー。
    
    【実務的なポイント】
    この時点ではまだタイヤ明細が登録されていない可能性が高いため、
    ここでは「見積の土台」を作ることに専念し、計算エンジンは
    「初期状態のセットアップ」として安全に実行します。
    """
    model = Estimate
    fields = ['customer_name', 'purchase_type', 'status']
    template_name = 'estimate/estimate_form.html'
    
    # 保存成功後のリダイレクト先（見積一覧など）
    success_url = reverse_lazy('estimate:estimate_list')

    @transaction.atomic
    def form_valid(self, form):
        """
        フォームのバリデーションが通った後の処理。
        DBへの保存と、初期状態での再計算を一つのトランザクションで行う。
        """
        # 親モデル（Estimate）をDBに保存
        response = super().form_valid(form)

        # 計算エンジンの実行
        # self.object は保存されたばかりの見積インスタンス。
        # recalc_all は内部で「タイヤ明細の有無」を判定している為、明細が空の状態でもエラーにならず合計金額（0円）をセット
        recalc_all(self.object)

        messages.success(
            self.request, 
            "見積の基本情報を保存しました。続けて明細を登録してください。"
        )
        
        return response


class EstimateDetailView(DetailView):
    """
    作成された見積の詳細画面。
    ここでは計算済みの「タイヤ明細」「諸費用」「合計金額」を表示します。
    """
    model = Estimate
    template_name = 'estimate/estimate_detail.html'
    context_object_name = 'estimate' # テンプレート側で使う変数名