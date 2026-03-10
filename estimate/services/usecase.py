from django.core.exceptions import ValidationError
from estimate.models import Estimate
# admin.py から usecase.recalc_estimate を呼ぶための「中継役」として残す!!!
from .calculator import recalc_all, sync_estimate_charges, recalc_estimate



# 見積につき2サイズまでOK(前後サイズ違い車種にも対応)と、複数台の混同を防ぐためのチェック機能
def validate_estimate_rules(estimate: Estimate):

    # 「取付作業あり」の場合のみ制限をかける
    if estimate.purchase_type == "install": # 交換作業
        # 1. 種類のチェック（ポルシェ・BMW等の前後異径を考慮して2種類まで）
        item_kinds = estimate.items.count()
        if item_kinds > 2:
            raise ValidationError(
                f"【台数制限エラー】作業予約は1台ずつです。現在{item_kinds}種類のタイヤが登録されています。2種類までに絞ってください。"
            )

        # 2. 合計本数のチェック（1台分＝スペア含め最大8本に制限）
        total_qty = sum(item.quantity for item in estimate.items.all())
        if total_qty > 8:
            raise ValidationError(
                f"【本数制限エラー】合計{total_qty}本登録されています。最大8本までにしてください。"
            )