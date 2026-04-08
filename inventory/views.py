from django.shortcuts import render
from django.contrib.auth.decorators import login_required  # ログイン必須にするためのデコレータ
from django.db.models import Q
from .models import Tire

@login_required
def tire_list(request):
    """
    【店員専用】在庫管理・曖昧検索ビュー
    店員が電話対応等で即座に在庫を確認できるよう、曖昧検索機能を搭載
    店員がログインしていること前提で、管理用のテーブルレイアウトを表示
    """
    # 🎯 見積作成画面から遷移してきた場合、その見積IDを保持して戻れるようにする
    estimate_id = request.GET.get('estimate_id')

    # 検索窓（幅やインチの一部入力）からの入力を取得
    front_size = request.GET.get('front_size', '').strip()
    rear_size = request.GET.get('rear_size', '').strip()

    # タイヤ情報を取得（ブランド情報を一括取得してSQLの発行回数を抑えるパフォーマンス最適化）
    tires = Tire.objects.select_related('brand_link').all()

    # サイズの入力がある場合はフィルタリング
    # 店員は「235」や「R20」などの断片的な情報で検索するため、icontains（部分一致）を使用
    if front_size and rear_size:
        # 前後でサイズが違う車両の場合、どちらかのサイズに合致するタイヤを両方リストアップする
        tires = tires.filter(Q(size_raw__icontains=front_size) | Q(size_raw__icontains=rear_size))
    elif front_size:
        # フロント（または1種類のみ）の入力がある場合
        tires = tires.filter(size_raw__icontains=front_size)
    elif rear_size:
        # リアのみの入力がある場合
        tires = tires.filter(size_raw__icontains=rear_size)

    # 🎯 使うテンプレートを店員用の admin 用に固定してレンダリング
    return render(request, 'inventory/tire_list_admin.html', {
        'tires': tires,
        'front_size': front_size,
        'rear_size': rear_size,
        'estimate_id': estimate_id,  # テンプレート側で「見積に戻る」ボタン等に使用
    })

def tire_list_public(request):
    """
    【お客様用】タイヤ閲覧ビュー
    ログイン不要。カード形式のレイアウト（tire_list.html）を表示します。
    """
    # 基本的な取得ロジックは同じ（継続販売ステータスのものだけに制限して表示）
    tires = Tire.objects.select_related('brand_link').filter(status_id=1) 
    
    return render(request, 'inventory/tire_list.html', {'tires': tires})