from decimal import Decimal
from django.db import transaction
from estimate.models import Estimate
from estimate.services.install_fee_service import apply_install_fees, remove_install_fees
from estimate.services.option_fee_service import apply_option_fees, remove_option_fees
from django.core.exceptions import ValidationError



#  純粋に金額だけを合計する関数（saveはしない）
def update_estimate_totals(estimate: Estimate) -> None:
    item_total = 0
    # タイヤ明細の合計
    for item in estimate.items.all():
        # タイヤのマスタ情報を取得
        tire = item.tire
        qty = item.quantity

        # 4本単位の計算（商と余り）
        num_sets = qty // 4   # 4で割ったセット数
        remainder = qty % 4   # 4で割った余りの本数


        # セット価格が設定されており、かつ1セット以上ある場合
        if num_sets > 0 and tire.set_price and tire.set_price > 0:
            # セット価格 × セット数 + 単体価格 × 余り
            subtotal = (num_sets * tire.set_price) + (remainder * item.unit_price)
        else:
            # 4本未満、またはセット価格がない場合はすべて単体価格
            subtotal = qty * item.unit_price

        # 明細の小計を更新して保存
        item.subtotal = subtotal
        item.save(update_fields=['subtotal'])
        item_total += subtotal

    # 諸費用（工賃など）を足して最終合計をセット
    charge_total = sum(charge.subtotal for charge in estimate.charges.all())
    # 見積本体にセット
    estimate.total_price = item_total + charge_total



# 全体の流れを管理するメイン関数（admin.py などから呼ぶ）
def recalc_estimate(estimate):
    item_total = 0

    # タイヤ明細(EstimateItem)を1行ずつループして計算
    for item in estimate.items.all():
        tire = item.tire
        qty = item.quantity

        # マスタ(tire)から最新価格を取得して明細(item)に上書きコピーすることで、常に最新のマスタ価格で見積が再計算される
        item.unit_price = tire.unit_price if tire.unit_price else 0
        item.set_price = tire.set_price if tire.set_price else 0

        # マスタから最新の価格をセット（表示用・保存用）
        # 計算に使うための変数
        unit_price = item.unit_price
        set_price = item.set_price

        # 4本セットの数とse、端数の数を算出
        # 例: 5本なら packs=1, remainder=1 / 8本なら packs=2, remainder=0
        num_sets = qty // 4   # セット数
        remainder = qty % 4   # 余りの本数

        # セット価格(set_price)が設定されており、かつ1セット(4本)以上ある場合
        if num_sets > 0 and set_price > 0:
            subtotal = (num_sets * set_price) + (remainder * unit_price)
        else:
            # 4本未満、またはセット価格がない場合はすべて単体価格
            subtotal = qty * unit_price

        # 明細の小計を更新して保存
        item.subtotal = subtotal
        item.save(update_fields=['unit_price', 'set_price', 'subtotal'])

        # ここで item_total に加算していく
        item_total += subtotal

    # 諸費用（工賃など）を合算
    charge_total = sum(charge.subtotal for charge in estimate.charges.all())

    # 見積本体の最終合計金額を更新
    estimate.total_price = item_total + charge_total
    # 合計金額と更新日時を保存（update_fieldsを指定して効率化）
    estimate.save(update_fields=['total_price', 'updated_at'])



    with transaction.atomic():
        # 工賃やオプションを適用（DBが更新される）
        if estimate.purchase_type == "install": # または estimate.PurchaseType.INSTALL
            apply_install_fees(estimate)
            apply_option_fees(estimate)
        else:
            remove_install_fees(estimate)
            remove_option_fees(estimate)

        # 更新された明細を元に、合計金額を算出
        update_estimate_totals(estimate)
        
        # 最後に一度だけ保存（update_fields で無限ループを防ぐ）
        estimate.save(update_fields=['total_price'])


# 1見積につき2サイズまでOK(前後サイズ違い車種にも対応)と、複数台の混同を防ぐためのチェック機能
def validate_estimate_rules(estimate: Estimate):
    # 「取付作業あり」の場合のみ制限をかける
    if estimate.purchase_type == "install": # 交換作業
        # 1. 種類のチェック（ポルシェ・BMW等の前後異径を考慮して2種類まで）
        item_kinds = estimate.items.count()
        if item_kinds > 2:
            raise ValidationError(
                f"【台数制限エラー】作業予約は1台ずつです。現在{item_kinds}種類のタイヤが登録されています。2種類（前後サイズ違い）までに絞ってください。"
            )
        
        # 2. 合計本数のチェック（1台分＝スペア含め最大6〜8本程度に制限）
        total_qty = sum(item.quantity for item in estimate.items.all())
        if total_qty > 8:
            raise ValidationError(
                f"【本数制限エラー】合計{total_qty}本登録されています。作業予約は1台分（最大8本まで）にしてください。"
            )