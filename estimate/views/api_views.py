import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
# モデルや計算ロジックのインポート
from inventory.models.tire import Tire
from ..services.calculator import calculate_purely

@csrf_exempt  # テストしやすくするために一旦付けて
@require_POST
def calculate_charges_api(request):
    """
    DBへの保存・削除を一切行わず、
    送られてきたタイヤ情報と手動入力された数量からメモリ上で諸費用を計算して返すAPI
    """
    try:
        data = json.loads(request.body)
        # JavaScriptから送られてくる諸費用の数量データを取り出す
        # JSから {'4_0': '2', '4_1': '0'} という形式で届く
        manual_charge_qtys = data.get('charge_qtys', {})
        items = data.get("items", [])
        purchase_type = data.get("purchase_type")

        # 1. タイヤ情報の準備
        # (これだけはDBを見る必要あり、保存はしない)
        processed_items = []
        for item in items:
            tire_id = int(item.get("tire_id") or 0)
            qty = int(item.get("quantity") or 0)

            if tire_id and qty > 0:
                # 🎯 DBアクセスは1回だけ！
                tire_master = Tire.objects.get(id=tire_id)

                processed_items.append({
                    "tire": tire_master,
                    "quantity": qty
                })

        # 2. 修正した計算機（Calculator）にデータを渡す
        # 引数に manual_charge_qtys を追加！
        # 計算機にそのまま渡す（計算機側はすでに index 対応済みなのでOK）
        results = calculate_purely(
            purchase_type=purchase_type, 
            items_data=processed_items,
            manual_charge_qtys=manual_charge_qtys
        )
        
        # 3. 計算結果を返す
        return JsonResponse({"charges": results})

    except Exception as e:
        import traceback
        print(traceback.format_exc()) # サーバーのターミナルにエラー詳細が出る
        return JsonResponse({"error": str(e)}, status=400)