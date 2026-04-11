from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required  # ログイン必須にするためのデコレータ
from django.db.models import Q
from django.contrib import messages
from .models import Tire, Order  # 🎯 Orderモデルをインポート
from audit.models import AuditLog  # 🎯 共通アプリのauditからインポート

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


@login_required
def order_create(request, tire_id):
    """
    【店員専用】発注ボタン押下時の処理
    直接ログを刻むのではなく、まずは「仮発注」レコードを作成して発注一覧画面へ誘導します。
    """
    tire = get_object_or_404(Tire, id=tire_id)

    # 🎯 仕様変更：AuditLogに直接書くのではなく、まずはOrderレコード（仮発注）を作る
    # quantityのデフォルトは、商用車等を考慮して「4本（1台分）」に設定
    order = Order.objects.create(
        tire=tire,
        quantity=4,                 # 仮の数量（後の画面で20本などに変更可能）
        status='DRAFT',             # 「仮発注」状態で作成
        user=request.user,          # 操作した店員
        cost_price_at_order=tire.cost_price # その時点の仕入れ値を記録
    )

    # 🎯 実務ポイント：接続元のIPアドレスを取得してメモに残す
    ip = request.META.get('REMOTE_ADDR')
    
    # 🎯 実務ポイント：AuditLogに操作記録（仮作成）を保存
    # target_type, target_id を使うことで、どのテーブルのどのデータか特定可能にしています
    AuditLog.objects.create(
        target_type="Order",             # 対象モデル名
        target_id=order.id,              # 作成したOrderのID
        action='DRAFT_CREATE',           # 操作種別（仮発注作成）
        actor=request.user,              # 操作したユーザー（石川さん等）
        note=f"IP:{ip} | {tire.brand} の仮発注を作成しました。数量確定待ち。", # メモ欄に詳細を記録
    )

    # 操作完了のメッセージを表示
    messages.info(request, f"【リスト追加】{tire.brand} を発注状況に追加しました。数量を確定させてください。")
    
    # 🎯 次のステップ：本来はここで 'inventory:order_list'（発注一覧画面）へ飛ばしたい
    # まだURLとViewを作っていないので、一旦在庫一覧に戻します。
    return redirect('inventory:tire_list')