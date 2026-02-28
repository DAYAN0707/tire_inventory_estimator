from decimal import Decimal
from django.db import transaction
from estimate.models import Estimate
from estimate.services.install_fee_service import apply_install_fees, remove_install_fees
from estimate.services.option_fee_service import apply_option_fees, remove_option_fees

#  純粋に金額だけを合計する関数（saveはしない）
def update_estimate_totals(estimate: Estimate) -> None:
    item_total = 0
    # タイヤ明細の合計
    for item in estimate.items.all():
        # タイヤのマスタ情報を取得
        tire = item.tire

        # 判定ロジック：4本ちょうど、かつセット価格が設定されている場合
        if item.quantity == 4 and tire.set_price and tire.set_price > 0:
            subtotal = tire.set_price
        else:
            # それ以外（1〜3本、または5本以上など）は単価 × 本数
            subtotal = item.quantity * item.unit_price

            # 明細側の小計（subtotal）もついでに更新しておくと表示が一致します
        item.subtotal = subtotal
        item.save(update_fields=['subtotal'])
        
        item_total += subtotal

    # 諸費用（工賃など）の合計
    charge_total = sum(charge.subtotal for charge in estimate.charges.all())
    
    # 見積本体にセット
    estimate.total_price = item_total + charge_total


# 全体の流れを管理するメイン関数（こちらを admin.py などから呼ぶ）
def recalc_estimate(estimate: Estimate) -> None:
    with transaction.atomic():
        # 1.工賃やオプションを適用（DBが更新される）
        if estimate.purchase_type == "install": # または estimate.PurchaseType.INSTALL
            apply_install_fees(estimate)
            apply_option_fees(estimate)
        else:
            remove_install_fees(estimate)
            remove_option_fees(estimate)

        # 2.更新された明細を元に、合計金額を算出
        update_estimate_totals(estimate)
        
        # 3:.最後に一度だけ保存（update_fields で無限ループを防ぐ）
        estimate.save(update_fields=['total_price'])
