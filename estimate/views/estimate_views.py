from django.views.generic import CreateView, DetailView, ListView
from django.shortcuts import render
from django import forms
from django.forms import inlineformset_factory
from django.http import JsonResponse
from inventory.models import Tire
from ..models import Estimate, EstimateItem, EstimateCharge, EstimateStatus
from django.urls import reverse
import json
from django.views.decorators.http import require_POST
from estimate.services.calculator import parse_tire_spec


# 見積明細（タイヤ）を複数入力するための設定
TireFormSet = inlineformset_factory(
    Estimate, EstimateItem, 
    fields=('tire', 'quantity'), 
    extra=2,  # 最初から表示する空の行数
    can_delete=True
)

def get_tire_info(request, tire_id):
    # タイヤのIDを受け取って、単価などを返すAPI
    try:
        tire = Tire.objects.get(pk=tire_id)
        return JsonResponse({
            'unit_price': tire.unit_price,
            'set_price': tire.set_price,
            # その他の必要な情報
        })
    except Tire.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


class EstimateCreateView(CreateView):
    model = Estimate
    template_name = "estimate/estimate_form.html"
    fields = ["purchase_type", "customer_name", "vehicle_name"]

    def get_success_url(self):
        # 保存が終わったら、今作った見積の詳細画面（detail）に飛ばす
        return reverse('estimate:estimate_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 画面に「タイヤ入力欄」のセットを渡す
        if self.request.POST:
            context['tire_formset'] = TireFormSet(self.request.POST)
        else:
            context['tire_formset'] = TireFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        tire_formset = context['tire_formset']

        if tire_formset.is_valid():
            # 保存する前に、ログインユーザーを作成者としてセットする
            form.instance.created_by = self.request.user 
            
            # ステータス等の不足情報をセット（例: "作成中"）
            initial_status = EstimateStatus.objects.first()
            if initial_status:
                form.instance.estimate_status = initial_status

            # Estimate本体を保存
            self.object = form.save()
            
            # タイヤ明細を保存
            tire_formset.instance = self.object
            tire_formset.save()

            # ここで super().form_valid(form) を呼ぶことで success_url に飛ぶ
            return super().form_valid(form)
        else:
            return self.render_to_response(self.get_context_data(form=form))



# 作成された見積の詳細画面
# ここでは計算済みの「タイヤ明細」「諸費用」「合計金額」を表示
class EstimateDetailView(DetailView):
    model = Estimate
    template_name = 'estimate/estimate_detail.html'
    context_object_name = 'estimate' # テンプレート側で使う変数名



@require_POST
def calculate_charges_api(request):
    """
    画面上のタイヤ構成から諸費用をリアルタイム計算して返すAPI
    """
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        purchase_type = data.get('purchase_type')

        # 1. 「持ち帰り」なら諸費用はなし
        if purchase_type == 'take_home':
            return JsonResponse({'charges': [], 'total': 0})

        total_work_qty = 0
        install_summary = {}
        
        # 2. 画面から送られてきた各行をループして集計
        for item in items:
            tire_id = item.get('tire_id')
            qty = int(item.get('quantity', 0))
            if not tire_id or qty <= 0:
                continue
            
            # タイヤ情報を取得
            tire = Tire.objects.get(id=tire_id)
            spec = parse_tire_spec(tire.size_raw)
            
            total_work_qty += qty
            
            # インチに合う工賃マスタを検索
            from ..models.masters.charge_master import ChargeMaster
            master = ChargeMaster.objects.filter(
                charge_type=ChargeMaster.ChargeType.INSTALL,
                min_inch__lte=spec.inch,
                max_inch__gte=spec.inch,
                is_active=True
            ).first()
            
            if master:
                mid = master.id
                if mid not in install_summary:
                    install_summary[mid] = {
                        'name': master.name,
                        'price': int(master.unit_price),
                        'qty': 0
                    }
                install_summary[mid]['qty'] += qty

        # 3. 返却用データ作成
        results = []
        # 工賃
        for res in install_summary.values():
            results.append({
                'name': res['name'],
                'price': res['price'],
                'qty': res['qty'],
                'subtotal': res['price'] * res['qty']
            })
        
        # バルブ・廃タイヤ
        if total_work_qty > 0:
            from ..models.masters.charge_master import ChargeMaster
            commons = ChargeMaster.objects.filter(
                charge_type__in=[ChargeMaster.ChargeType.VALVE, ChargeMaster.ChargeType.WASTE],
                is_active=True
            )
            for m in commons:
                results.append({
                    'name': m.name,
                    'price': int(m.unit_price),
                    'qty': total_work_qty,
                    'subtotal': int(m.unit_price) * total_work_qty
                })

        return JsonResponse({'charges': results})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)