import json
from django.views.generic import ListView, CreateView, DetailView
from django.forms import inlineformset_factory
from django.urls import reverse
from django.shortcuts import redirect
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from inventory.models import Tire
from ..models import Estimate, EstimateItem, EstimateStatus
from ..forms import EstimateTireForm
from ..services.usecase import EstimateUseCase

# ユーザーモデルを取得（カスタムユーザーにも対応できる標準的な書き方）
User = get_user_model()

# ==========================================
# 1. フォームセットの設定
# ==========================================
# Estimate（親）と EstimateItem（子）を1つの画面で扱うための魔法のセット
EstimateTireFormSet = inlineformset_factory(
    Estimate,       # 親モデル
    EstimateItem,   # 子モデル
    form=EstimateTireForm, # 各行に使用するフォーム
    extra=1,        # 最初から表示しておく空行の数
    can_delete=True # 行の削除を許可
)

class EstimateListView(ListView):
    """見積の一覧を表示するView"""
    model = Estimate
    template_name = 'estimate/estimate_list.html'
    context_object_name = 'estimates'
    ordering = ['-created_at'] # 新しい順に並べる

class EstimateCreateView(CreateView):
    """見積を新規作成するView"""
    model = Estimate
    template_name = "estimate/estimate_form.html"
    # 画面に表示する「見積本体」の項目
    fields = ["purchase_type", "customer_name", "vehicle_name"]

    # --- [保存成功後の処理] ---
    # 保存が成功した後に、作成された見積の詳細画面(pk)へ自動で飛ばす
    def get_success_url(self):
        return reverse('estimate:estimate_detail', kwargs={'pk': self.object.pk})

    # --- [画面に渡すデータの準備] ---
    # HTMLテンプレートで使いたい変数（tires_jsonやformset）をセットする
    def get_context_data(self, **kwargs):
        # 親クラスの標準的なcontextを取得
        context = super().get_context_data(**kwargs)
        
        # タイヤのマスタデータを取得してJSに渡す（フロントでの単価・小計計算用）
        tires_list = list(
            Tire.objects.values("id", "unit_price", "set_price")
        )
        context["tires_json"] = json.dumps(tires_list)

        # 画面に表示する「タイヤ明細（フォームセット）」を準備
        if self.request.POST:
            # 保存ボタンが押された時（入力データがある時）
            context['tire_formset'] = EstimateTireFormSet(self.request.POST)
        else:
            # 最初に画面を開いた時（空のフォームを表示する時）
            context['tire_formset'] = EstimateTireFormSet()

        return context

    # --- [保存ボタンが押された時のバリデーションと実行] ---
    # フォームの入力内容に問題がなければ、この関数が呼ばれる
    def form_valid(self, form):
        # get_context_dataを呼び出して、現在のフォームセットの状態を取得
        context = self.get_context_data()
        tire_formset = context['tire_formset']

        # 1. タイヤ明細（フォームセット）の入力チェック（必須項目漏れなどがないか）
        if tire_formset.is_valid():
            try:
                # 親モデル（Estimate）のインスタンスを「保存直前」の状態で生成
                estimate = form.save(commit=False)
                
                # --- ✅ 作成者（created_by）のセットロジック ---
                # ログイン状態によってセットするユーザーを切り替える（IntegrityError対策）
                if self.request.user.is_authenticated:
                    # ログイン中ならそのユーザーをセット
                    estimate.created_by = self.request.user
                else:
                    # 未ログインならDB内の「最初の一人（管理者等）」を自動割り当て
                    # 開発環境やログイン機能未実装時でも保存を止めないための安全策
                    first_user = User.objects.first()
                    if first_user:
                        estimate.created_by = first_user
                    else:
                        # ユーザーが一人もいない致命的な状況
                        form.add_error(None, "ユーザーが登録されていないため保存できません。")
                        return self.render_to_response(self.get_context_data(form=form))

                # --- 2. ステータスの初期値セット ---
                # マスタから「作成中」を取得。なければエラーを表示。
                try:
                    status_draft = EstimateStatus.objects.get(status_name='作成中')
                    estimate.estimate_status = status_draft
                except EstimateStatus.DoesNotExist:
                    form.add_error(None, "マスタに '作成中' というステータスが必要です。")
                    return self.render_to_response(self.get_context_data(form=form))
                
                # --- 👐 手入力データの解析（諸費用テーブルから集約） ---
                # JS側で input name="charge_qtys[ID_Index]" となっている値を辞書にまとめる
                manual_dict = {}
                for key, val in self.request.POST.items():
                    if key.startswith("charge_qtys["):
                        # "charge_qtys[4_0]" -> "4_0" というキーを取り出す
                        manual_key = key.replace("charge_qtys[", "").replace("]", "")
                        if val is not None and val != "":
                            manual_dict[manual_key] = int(val)

                # デバッグ：サーバー側のターミナルで手入力内容を確認できる
                print(f"DEBUG: 受信した手入力データ -> {manual_dict}")

                # --- 3. 【心臓部】UseCaseの呼び出し ---
                # 計算ロジック（ランフラット判定や合計計算など）を実行し、最終的なDB保存を行う
                self.object = EstimateUseCase.create_estimate(
                    estimate_instance=estimate,
                    tire_formset=tire_formset,
                    user=estimate.created_by,
                    manual_data=manual_dict
                )
                
                # 全て完了したら詳細画面へリダイレクト
                return redirect(self.get_success_url())

            except Exception as e:
                # UseCase内や保存処理でエラーが出た場合のキャッチ
                form.add_error(None, f"システムエラーが発生しました: {str(e)}")
                return self.render_to_response(self.get_context_data(form=form))
        else:
            # タイヤ明細（フォームセット）の入力内容に不備がある場合
            return self.render_to_response(self.get_context_data(form=form))

class EstimateDetailView(DetailView):
    """作成された見積の最終結果を確認するView"""
    model = Estimate
    template_name = 'estimate/estimate_detail.html'
    context_object_name = 'estimate'