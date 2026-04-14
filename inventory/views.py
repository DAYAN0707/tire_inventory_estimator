from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required  # ログイン必須にするためのデコレータ
from django.db.models import Q
from django.contrib import messages
from .models import Tire, Order, Brand
from audit.models import AuditLog  # 🎯 共通アプリのauditからインポート
from django.views.generic import CreateView, UpdateView, ListView
from django.urls import reverse_lazy

def tire_list(request):
    """
    【店員もお客さんも共通】カード型タイヤ一覧画面
    """
    # 1. まず全データを取得
    queryset = Tire.objects.all()

    # パラメータ取得
    front_size = request.GET.get('front_size') or None
    rear_size = request.GET.get('rear_size') or None
    estimate_id = request.GET.get('estimate_id')

    # 検索ロジック
    if front_size and rear_size:
        # 前後のサイズどちらかにヒットすればOK
        queryset = queryset.filter(
            Q(size_raw__icontains=front_size) |
            Q(size_raw__icontains=rear_size)
        )
    elif front_size:
        # 前輪サイズのみで検索
        queryset = queryset.filter(size_raw__icontains=front_size)
    elif rear_size:
        # 後輪サイズのみで検索
        queryset = queryset.filter(size_raw__icontains=rear_size)

    # コンテキストに詰めて返す
    context = {
        'tires': queryset,
        'front_size': front_size or '', # テンプレート表示用にNoneなら空文字に
        'rear_size': rear_size or '',
        'estimate_id': estimate_id,
    }
    return render(request, 'inventory/tire_list.html', context)

@login_required
def tire_list_admin(request):
    """
    【店員専用】在庫管理・リスト型画面
    役割：店内のPCで、在庫数、仕入れ値、発注ボタンを管理するための「裏方」画面
    機能：1. インチ数や幅による曖昧検索 2. 見積作成中のタイヤ選択からの戻り先保持
    """
    # 見積作成の途中で在庫確認に来た場合、元の見積画面に戻れるようIDを取得
    estimate_id = request.GET.get('estimate_id')

    # 検索窓に入力されたサイズ情報を取得
    front_size = request.GET.get('front_size', '').strip()
    rear_size = request.GET.get('rear_size', '').strip()

    # パフォーマンス対策：ブランド情報を一括取得(JOIN)してデータベースへの負荷を軽減
    tires = Tire.objects.select_related('brand_link').all()

    # 部分一致（icontains）によるフィルタリング(店員の「235」などの断片的な入力に対応)
    if front_size and rear_size:
        tires = tires.filter(Q(size_raw__icontains=front_size) | Q(size_raw__icontains=rear_size))
    elif front_size:
        tires = tires.filter(size_raw__icontains=front_size)
    elif rear_size:
        tires = tires.filter(size_raw__icontains=rear_size)

    # 🎯 管理用の「tire_list_admin.html」を呼び出す（URLかぶっていた問題を解消）
    return render(request, 'inventory/tire_list_admin.html', {
        'tires': tires,
        'front_size': front_size,
        'rear_size': rear_size,
        'estimate_id': estimate_id,
    })

@login_required
def order_create(request, tire_id):
    """
    【店員専用】在庫画面から「発注」ボタンを押した時の初期処理
    役割：いきなり確定させるのではなく、まずは「発注状況（DRAFT）」というレコードを作る
    """
    tire = get_object_or_404(Tire, id=tire_id)
    
    # 仮発注（ステータス：DRAFT）として保存。本数は一旦4本（1台分）をデフォルトに設定
    order = Order.objects.create(
        tire=tire,
        quantity=4,
        status='DRAFT',
        user=request.user,
        cost_price_at_order=tire.cost_price # 発注時点の価格を記録（後で値上がりしても大丈夫なように）
    )

    # 操作ログ（AuditLog）への記録。いつ、誰が、どのタイヤを操作したか証拠を残す
    ip = request.META.get('REMOTE_ADDR')
    AuditLog.objects.create(
        target_type="Order",
        target_id=order.id,
        action='DRAFT_CREATE',
        actor=request.user,
        note=f"IP:{ip} | {tire.brand} の仮発注を作成しました。数量確定待ち。"
    )

    messages.info(request, f"【リスト追加】{tire.brand} を発注状況に追加しました。数量を調整してください。")
    return redirect('inventory:order_list')

@login_required
def order_list(request):
    """
    【店員専用】発注一覧画面
    役割：現在「仮発注」の状態にあるものや、過去の確定・取消履歴を一覧表示する
    """
    # 作成日時の新しい順（降順）に並べ替えて取得
    orders = Order.objects.select_related('tire', 'user').all().order_by('-created_at')
    return render(request, 'inventory/order_list.html', {'orders': orders})

@login_required
def order_confirm(request, order_id):
    """
    【店員専用】発注内容（本数）を確定させる処理
    役割：発注一覧画面で入力された本数を反映し、ステータスを「確定」に書き換える
    """
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        new_quantity = request.POST.get('quantity')
        order.quantity = new_quantity
        order.status = 'CONFIRMED' # ここで「確定」に切り替え
        order.save()

        # 確定した事実をログに保存
        ip = request.META.get('REMOTE_ADDR')
        AuditLog.objects.create(
            target_type="Order",
            target_id=order.id,
            action='ORDER_CONFIRMED',
            actor=request.user,
            note=f"IP:{ip} | {order.tire.brand} を {new_quantity}本 で発注確定しました。"
        )
        messages.success(request, f"【発注確定】{order.tire.brand} を{new_quantity}本で確定しました。")
    return redirect('inventory:order_list')

@login_required
def order_cancel(request, order_id):
    """
    【店員専用】発注を取り消す処理
    役割：間違えて追加した発注を消す。ただし、履歴管理のためレコードは消さず「CANCELLED」にする
    """
    order = get_object_or_404(Order, id=order_id)
    order.status = 'CANCELLED'
    order.save()

    ip = request.META.get('REMOTE_ADDR')
    AuditLog.objects.create(
        target_type="Order",
        target_id=order.id,
        action='ORDER_CANCELLED',
        actor=request.user,
        note=f"IP:{ip} | {order.tire.brand} の発注を取り消しました。"
    )
    messages.warning(request, f"【発注取消】{order.tire.brand} の発注を取り消しました。")
    return redirect('inventory:order_list')


class BrandCreateView(CreateView):
    model = Brand
    fields = ['name', 'comment']
    template_name = 'inventory/brand_form.html'
    success_url = reverse_lazy('inventory:brand_list')

class BrandUpdateView(UpdateView):
    model = Brand
    fields = ['name', 'comment']
    template_name = 'inventory/brand_form.html'
    success_url = reverse_lazy('inventory:brand_list')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        
        # 削除ボタン押下時の処理
        if 'delete' in request.POST:
            self.object.delete()
            return redirect(self.success_url)
            
        return super().post(request, *args, **kwargs)

class BrandListView(ListView):
    model = Brand
    template_name = 'inventory/brand_list.html'
    context_object_name = 'brands'
    ordering = ['name']