from django.views.generic import CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Estimate
from inventory.models import Tire
from django.views.generic import DetailView


class EstimateCreateView(LoginRequiredMixin, CreateView):
    model = Estimate
    fields = ["purchase_type", "customer_name", "vehicle_name"]
    template_name = "estimate/estimate_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tire_id = self.request.GET.get("tire_id")

        if tire_id:
            tire = Tire.objects.get(pk=tire_id)
            context["unit_price"] = tire.price
            context["four_price"] = tire.set_price

        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.estimate_status_id = 1  # ← 作成中ID確認！
        return super().form_valid(form)
    


    
class EstimateDetailView(DetailView):
    model = Estimate
    template_name = "estimate/estimate_detail.html"