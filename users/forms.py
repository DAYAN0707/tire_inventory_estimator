from django import forms # Djangoのフォーム機能を利用するためのインポート
from django.contrib.auth.forms import AuthenticationForm # Djangoの組み込み認証フォームをベースにカスタマイズするためのインポート
from django.contrib.auth import authenticate # 認証処理を行うための関数をインポート
from .models import User  # 同じフォルダのmodels.pyからUserを読み込む

# スタッフログインフォーム（従業員IDとパスワードでログインするフォーム）
class StaffLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="ログインID",
        widget=forms.TextInput(attrs={
            'class': 'form-control', #
            'placeholder': '6桁の従業員IDを入力',
            'maxlength': '6',
        })
    )

    # パスワードフィールドはAuthenticationFormのまま（Djangoの組み込み機能を利用）
    def clean(self):
        staff_id = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if staff_id and password:
            try:
                # 従業員IDからユーザーを探す
                user_obj = User.objects.get(staff_id=staff_id)
                # Django内部の認証（username）に通す
                self.user_cache = authenticate(
                    self.request,
                    username=user_obj.username,
                    password=password
                )
            except User.DoesNotExist:
                self.user_cache = None

        # 認証に失敗した場合はエラーを出す
        if self.user_cache is None:
            raise forms.ValidationError("IDまたはパスワードが正しくありません。")

        return self.cleaned_data
