from django.shortcuts import redirect # 画面表示、オブジェクト取得、リダイレクトのためのショートカット関数
from django.urls import reverse_lazy # URLの逆引きに使用（成功後のリダイレクト先など）
from django.views.generic import ListView, CreateView, UpdateView # クラスベースビューをインポート
from django.contrib.auth import get_user_model # カスタムユーザーモデルを取得（image_480fbe.pngの項目を扱うため）
from django.utils.decorators import method_decorator # クラスベースViewにデコレータを適用するためのインポート
from django.contrib.auth.views import LoginView # Django標準のログインビューをインポート
from .forms import StaffLoginForm # カスタムログインフォームをインポート
from .utils import stop_demo_user # デモユーザーの操作を制限するユーティリティ関数をインポート

# カスタムユーザーモデルを取得（image_480fbe.pngの項目を扱うため）
User = get_user_model()

# --- 既存のログイン機能 ---
class StaffLoginView(LoginView):
    form_class = StaffLoginForm # カスタムログインフォームを使用
    template_name = 'users/login.html' # ログイン画面のテンプレートを指定
    
    # ログイン成功後のリダイレクト先を指定
    def get_success_url(self):
        return self.get_redirect_url() or reverse_lazy('estimate:manager_dashboard')


# --- 1. ユーザー一覧画面 ---
class UserListView(ListView):
    model = User
    template_name = 'users/user_list.html' # ユーザー一覧画面のテンプレートを指定
    context_object_name = 'users' # テンプレート内でユーザーリストを参照する際の名前
    ordering = ['-is_staff', 'staff_id'] # スタッフユーザーを上に、次に従業員ID順で並べる

# --- 2. ユーザー登録画面 ---
@method_decorator(stop_demo_user, name='dispatch')  # デモユーザーの操作を制限するデコレータをクラスベースViewのdispatchメソッドに適用
class UserCreateView(CreateView):
    model = User
    fields = ['username', 'staff_id', 'staff_name', 'is_staff', 'is_active'] # フォームに表示するフィールドを指定
    template_name = 'users/user_form.html' # ユーザー登録・編集画面のテンプレートを指定
    success_url = reverse_lazy('users:user_list') # 登録成功後のリダイレクト先をユーザー一覧画面に設定

# --- 3. ユーザー編集・削除画面 ---
@method_decorator(stop_demo_user, name='dispatch')  # デモユーザーの操作を制限するデコレータをクラスベースViewのdispatchメソッドに適用
class UserUpdateView(UpdateView):
    model = User
    fields = ['username', 'staff_id', 'staff_name', 'is_staff', 'is_active'] # フォームに表示するフィールドを指定
    template_name = 'users/user_form.html' # ユーザー登録・編集画面のテンプレートを指定
    success_url = reverse_lazy('users:user_list') # 編集成功後のリダイレクト先をユーザー一覧画面に設定

    # ここで削除も処理するため、postメソッドをオーバーライド
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        
        # 諸費用設定と同じ「削除」ロジック
        if 'delete' in request.POST:
            self.object.delete()
            # 削除後はユーザー一覧にリダイレクト
            return redirect(self.success_url)

        # フォームのバリデーションと保存処理
        form = self.get_form()
        if form.is_valid():
            # フォームからユーザーオブジェクトを作成（まだ保存しない）
            user = form.save(commit=False)
            
            # 🎯スイッチの状態を強制的に反映させる
            # チェックボックスはOFFだとPOSTデータに含まれないため
            user.is_staff = 'is_staff' in request.POST
            user.is_active = 'is_active' in request.POST
            
            # フォームの内容を保存する（ユーザーオブジェクトをデータベースに保存）
            user.save()
            return redirect(self.success_url)
        # フォームが無効な場合はエラーを表示して同じページに戻す
        return self.form_invalid(form)