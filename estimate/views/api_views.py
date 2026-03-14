import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from ..services.usecase import EstimateUseCase

@require_POST
def calculate_charges_api(request):
    """
    JSからの計算リクエストをUseCaseへ橋渡しするだけの窓口
    """
    try:
        data = json.loads(request.body)
        items = data.get("items", [])
        purchase_type = data.get("purchase_type")

        # 業務ロジック（計算）は全て UseCase に任せる
        result = EstimateUseCase.calculate_charges(items, purchase_type)

        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)