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


# ユーザー登録フォーム（管理画面で使用）
class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label="パスワード",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'パスワードを入力'})
    )
    password2 = forms.CharField(
        label="パスワード確認",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'もう一度入力'})
    )

    class Meta:
        model = User
        # 既存の fields をそのままここにコピーして、パスワードフィールドはフォームの外で定義する（責務の分離）
        fields = ['username', 'staff_id', 'staff_name', 'is_staff', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'staff_id': forms.TextInput(attrs={'class': 'form-control'}),
            'staff_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    # パスワードの一致チェック
    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password1")
        p2 = cleaned_data.get("password2")

        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("パスワードが一致しません。")
        return cleaned_data

    # 保存時にパスワードをハッシュ化するロジック（責務の分離）
    def save(self, commit=True):
        user = super().save(commit=False)
        # 安全に暗号化してセット
        user.set_password(self.cleaned_data["password1"])
        
        if commit:
            user.save()
        return user