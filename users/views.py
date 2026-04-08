from django.contrib.auth.views import LoginView
from .forms import StaffLoginForm

class StaffLoginView(LoginView):
    form_class = StaffLoginForm
    template_name = 'users/login.html'