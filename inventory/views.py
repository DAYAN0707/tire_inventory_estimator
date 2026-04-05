from django.shortcuts import render
from .models import Tire
from django.db.models import Q

# タイヤの在庫状況を表示するビュー
def tire_list(request):
    # 🎯 見積IDをURLパラメータ (?estimate_id=123) から取得
    estimate_id = request.GET.get('estimate_id')

    # 検索窓からの入力を取得
    front_size = request.GET.get('front_size', '').strip()
    rear_size = request.GET.get('rear_size', '').strip()

    # タイヤ情報を取得（関連するブランド情報も一緒に取得してパフォーマンス最適化）
    tires = Tire.objects.select_related('brand_link').all()

    # サイズの入力がある場合はフィルタリング（前後両方入力された場合は両方に合致するものを表示）
    if front_size and rear_size:
        # 前後でサイズが違う場合、どちらかのサイズに合致するタイヤを両方出す
        tires = tires.filter(Q(size_raw__icontains=front_size) | Q(size_raw__icontains=rear_size))
    elif front_size:
        # 1種類だけ入力された場合
        tires = tires.filter(size_raw__icontains=front_size)

    # 画面にタイヤ情報と検索条件、および見積IDを渡してレンダリング
    return render(request, 'inventory/tire_list.html', {
        'tires': tires,
        'front_size': front_size,
        'rear_size': rear_size,
        'estimate_id': estimate_id,  # 🎯 テンプレートのフォーム作成に使用
    })