from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView
from .forms import StaffLoginForm

# カスタムユーザーモデルを取得（image_480fbe.pngの項目を扱うため）
User = get_user_model()

# --- 既存のログイン機能 ---
class StaffLoginView(LoginView):
    form_class = StaffLoginForm
    template_name = 'users/login.html'

# --- 1. ユーザー一覧画面 ---
class UserListView(ListView):
    model = User
    template_name = 'users/user_list.html'
    context_object_name = 'users'
    ordering = ['-is_staff', 'staff_id']

# --- 2. ユーザー登録画面 ---
class UserCreateView(CreateView):
    model = User
    fields = ['username', 'staff_id', 'staff_name', 'is_staff', 'is_active']
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users:user_list')

# --- 3. ユーザー編集・削除画面 ---
class UserUpdateView(UpdateView):
    model = User
    fields = ['username', 'staff_id', 'staff_name', 'is_staff', 'is_active']
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users:user_list')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        
        # 諸費用設定と同じ「削除」ロジック
        if 'delete' in request.POST:
            self.object.delete()
            return redirect(self.success_url)

        form = self.get_form()
        if form.is_valid():
            user = form.save(commit=False)
            
            # 🎯スイッチの状態を強制的に反映させる
            # チェックボックスはOFFだとPOSTデータに含まれないため
            user.is_staff = 'is_staff' in request.POST
            user.is_active = 'is_active' in request.POST
            
            user.save()
            return redirect(self.success_url)
        
        return self.form_invalid(form)