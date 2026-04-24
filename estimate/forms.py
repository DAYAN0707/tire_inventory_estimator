from django import forms
from .models import Estimate, EstimateItem


# 見積のフォームクラス（管理画面やフロントエンドで使用）
class EstimateForm(forms.ModelForm):
    class Meta:
        model = Estimate
        fields = ['purchase_type', 'customer_name', 'vehicle_name']
        widgets = {
            # 購入区分に JS用のクラスを追加
            'purchase_type': forms.Select(attrs={'class': 'form-select'}),
            'customer_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例：寶井 秀人 '}),
            'vehicle_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例：プリウス'}),
        }

    # フォームの初期化時に、購入タイプに応じて車種の必須設定を動的に変更する（フロントエンドでのユーザビリティ向上）
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 諸費用マスタ(ChargeMaster)の選択肢を「有効(is_active=True)なもの」だけに絞り込む
        # これにより、View側で「無効化」したマスタが新規見積の選択肢に出なくなる（過去の見積データの整合性を保ちつつ、ユーザビリティを向上させるための措置）
        if 'cost_master' in self.fields:
            from estimate.models import ChargeMaster
            self.fields['cost_master'].queryset = ChargeMaster.objects.filter(is_active=True)

        # 初期状態では車種は必須ではないが、購入タイプが取付作業ありの場合は車種を必須にする
        self.fields['vehicle_name'].required = False

        purchase_type = (
            self.data.get('purchase_type') # フォームの送信データから購入タイプを取得(新規作成時や更新時の両方に対応)
            or self.initial.get('purchase_type') # フォームの初期値から購入タイプを取得(管理画面で初期値をセットしている場合に対応)
            or getattr(self.instance, 'purchase_type', None) # フォームのインスタンスの値から購入タイプを取得(既存の見積を編集する場合に対応)
        )

        # フォームのデータや初期値、インスタンスの値から購入タイプを取得して、取付作業ありの場合は車種を必須にする
        if purchase_type == 'install':
            self.fields['vehicle_name'].required = True

    # 購入タイプが取付作業ありの場合、車種が必須になるようにバリデーションを追加する（サーバーサイドでのデータ整合性を担保）
    def clean_vehicle_name(self):
        purchase_type = (
            self.cleaned_data.get('purchase_type')
            or getattr(self.instance, 'purchase_type', None)
        )

        vehicle_name = self.cleaned_data.get('vehicle_name')

        if purchase_type == 'install' and not vehicle_name:
            raise forms.ValidationError('取付作業の場合は車種が必須です')

        return vehicle_name

# タイヤ明細用のフォームクラス
class EstimateTireForm(forms.ModelForm):
    class Meta:
        model = EstimateItem
        fields = ['tire', 'quantity']
        widgets = {
            # タイヤ選択に js-tire-select クラスを追加（JSがこの名前を探す）
            'tire': forms.Select(attrs={'class': 'form-select js-tire-select'}),
            # 数量入力に js-quantity-input クラスを追加（JSがこの名前を探す）
            'quantity': forms.NumberInput(attrs={'class': 'form-control js-quantity-input', 'min': 1}),
        }



class EstimateItemInlineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        
        # 削除フラグが立っていないフォームの合計本数と種類をカウント
        total_qty = 0
        active_kind_count = 0

        # メインフォーム（EstimateForm）の購入区分を取得
        purchase_type = self.instance.purchase_type
        is_takeout = (purchase_type == 'takeout')

        for form in self.forms:
            # 削除チェックがついている、またはデータが空のフォームは無視
            if self._should_delete_form(form) or not form.cleaned_data:
                continue
            
            # --- 【英語エラーの修正】 ---
            # .get('quantity') が None（空欄）を返す可能性があるので "or 0" を付ける
            qty = form.cleaned_data.get('quantity') or 0
            tire = form.cleaned_data.get('tire')

            if tire and qty > 0:
                total_qty += qty
                active_kind_count += 1

        # エラー判定（「持ち帰り」でない場合のみ実行）
        if not is_takeout:
            # 台数制限（種類）のチェック
            if active_kind_count > 2:
                self.add_error(None, f"【台数制限エラー】現在{active_kind_count}種類選択中です。交換作業ご希望の場合は、1台分（前後サイズ違いのお車は最大2サイズ可）までです。")
            
            # 本数制限のチェック
            if total_qty > 8:
                self.add_error(None, f"【本数制限エラー】現在{total_qty}本選択中です。交換作業ご希望の場合は、最大8本までにしてください。")