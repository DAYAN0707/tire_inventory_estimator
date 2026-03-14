from django.db import transaction
from django.core.exceptions import ValidationError
from inventory.models import Tire
# 内部的な計算ロジックやマスタを先頭でインポート
from ..models import Estimate, EstimateItem, EstimateStatus
from ..models.masters.charge_master import ChargeMaster
from .calculator import recalc_estimate, parse_tire_spec

# --- バリデーションロジック ---
def validate_estimate_rules(estimate: Estimate):
    """
    見積作成時の業務ルールチェック
    """
    # 「取付作業あり」の場合のみ制限をかける
    if estimate.purchase_type == Estimate.PurchaseType.INSTALL:
        # 1. 種類のチェック（前後異径を考慮して2種類まで）
        item_kinds = estimate.items.count()
        if item_kinds > 2:
            raise ValidationError(f"【台数制限エラー】現在{item_kinds}種類選択中です。交換作業ご希望の場合は、1台分(前後サイズ違いのお車など、最大2サイズ選択可能)までにしてください。")

        # 2. 合計本数のチェック（1台分＝スペア含め最大8本に制限）
        total_qty = sum(item.quantity for item in estimate.items.all())
        if total_qty > 8:
            raise ValidationError(f"【本数制限エラー】現在{total_qty}本選択中です。交換作業ご希望の場合は、最大8本までにしてください。")

class EstimateUseCase:
    """
    見積に関する業務ロジックを集約（Viewを薄く保つためのService層）
    """

    @staticmethod
    def calculate_charges(items, purchase_type):
        """
        JSからのリクエストに応じて工賃等の諸費用を計算する
        """
        # 持ち帰りの場合は諸費用なし
        if purchase_type == Estimate.PurchaseType.TAKE_HOME:
            return {"charges": [], "total": 0}

        total_work_qty = 0
        install_summary = {}

        for item in items:
            tire_id = item.get("tire_id")
            qty = int(item.get("quantity", 0))

            if not tire_id or qty <= 0:
                continue

            tire = Tire.objects.get(id=tire_id)
            spec = parse_tire_spec(tire.size_raw)

            # インチ数に合致するアクティブな工賃を取得
            master = ChargeMaster.objects.filter(
                charge_type=ChargeMaster.ChargeType.INSTALL,
                min_inch__lte=spec.inch,
                max_inch__gte=spec.inch,
                is_active=True
            ).first()

            if master:
                if master.id not in install_summary:
                    install_summary[master.id] = {
                        "name": master.name,
                        "price": int(master.unit_price),
                        "qty": 0
                    }
                install_summary[master.id]["qty"] += qty
            
            total_work_qty += qty

        results = []
        for res in install_summary.values():
            results.append({
                "name": res["name"],
                "price": res["price"],
                "qty": res["qty"],
                "subtotal": res["price"] * res["qty"]
            })

        # 共通費用（バルブ・廃タイヤ）を取得
        commons = ChargeMaster.objects.filter(
            charge_type__in=[ChargeMaster.ChargeType.VALVE, ChargeMaster.ChargeType.WASTE],
            is_active=True
        )

        for m in commons:
            results.append({
                "name": m.name,
                "price": int(m.unit_price),
                "qty": total_work_qty,
                "subtotal": int(m.unit_price) * total_work_qty
            })

        return {"charges": results}

    @staticmethod
    def create_estimate(estimate_instance, tire_formset, user):
        """
        見積本体と明細をアトミックに保存し、バリデーションと再計算を行う
        """
        with transaction.atomic():
            estimate_instance.created_by = user
            if not estimate_instance.estimate_status:
                estimate_instance.estimate_status = EstimateStatus.objects.first()

            estimate_instance.save()
            tire_formset.instance = estimate_instance
            tire_formset.save()

            # 業務ルール違反がないかチェック
            validate_estimate_rules(estimate_instance)
            # 保存データに基づいて最終計算（サーバーサイド）
            recalc_estimate(estimate_instance)

            return estimate_instance