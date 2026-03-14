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