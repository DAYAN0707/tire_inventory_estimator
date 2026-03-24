from django.db import transaction
from django.core.exceptions import ValidationError
from inventory.models import Tire
# 内部的な計算ロジックやマスタを先頭でインポート
from ..models import Estimate, EstimateItem, EstimateStatus
from ..models.masters.charge_master import ChargeMaster
from .calculator import recalc_all, parse_tire_spec
from .calculator import sync_estimate_charges
from django.db import transaction

#  バリデーションロジック
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
    def calculate_purely(purchase_type, items_data, manual_charge_qtys=None):
        # 【前提】
        # items_data: [{'tire': Tireオブジェクト, 'quantity': 2}, ...]
        # manual_charge_qtys: {'4_0': '2', '6_1': '0'} のような形式（JSから送信）
        
        # 【仕様】
        # 工賃：手入力優先（0 OK）
        # バルブ・廃タイヤ：手入力優先（0 OK）
        # ランフラット：手入力不可、工賃合計に強制連動

        # =========================
        # 0. 持ち帰りは即終了
        # =========================
        if purchase_type == 'take_home':
            return []

        results = []  # ← 最終的にフロントへ返す配列

        # =========================
        # 1. 全体の基礎データ集計
        # =========================
        total_tire_qty = 0   # タイヤ総本数（購入本数）
        total_work_qty = 0   # 交換作業の合計本数（工賃ベース）
        total_rft_qty = 0    # RFTタイヤの本数

        # 🎯 工賃のマスタID（あなたの環境では 4）
        INSTALL_IDS = ['4']

        for item in items_data:
            # 🎯 dictで統一されている前提
            tire = item['tire']
            qty = int(item.get('quantity', 0))

            total_tire_qty += qty
            total_work_qty += qty  # デフォルトは購入本数＝作業本数

            # 🎯 RFT判定（サイズ文字列に含まれる）
            if tire.size_raw and "RFT" in tire.size_raw:
                total_rft_qty += qty

        # =========================
        # 2. 手入力から「工賃合計」を再計算
        # =========================
        # 🎯 ここがRFT連動の基礎になる超重要ポイント
        manual_work_total = 0

        if manual_charge_qtys:
            for key, val in manual_charge_qtys.items():
                # key例: "4_0" → "4" を取り出す
                master_id = key.split('_')[0]

                # 🎯 工賃のIDだけ拾う
                if master_id in INSTALL_IDS:
                    manual_work_total += int(val or 0)

        # 🎯 手入力がある場合は「作業本数」を上書き
        if manual_charge_qtys is not None:
            total_work_qty = manual_work_total

        # =========================
        # 3. 工賃（INSTALL）
        # =========================
        install_masters = ChargeMaster.objects.filter(
            charge_type=ChargeMaster.ChargeType.INSTALL,
            is_active=True
        )

        for m in install_masters:
            qty = 0  # 初期化

            # 🎯 手入力優先（0もそのまま採用）
            if manual_charge_qtys:
                for key, val in manual_charge_qtys.items():
                    if str(m.id) == key.split('_')[0]:
                        qty = int(val or 0)
                        break
            else:
                # 初期表示（デフォルト）
                qty = total_tire_qty

            results.append({
                "master_id": m.id,
                "name": m.name,
                "qty": qty,
                "price": int(m.unit_price),
                "subtotal": int(m.unit_price * qty)
            })

        # =========================
        # 4. 共通費用（バルブ・廃タイヤ）
        # =========================
        commons = ChargeMaster.objects.filter(
            charge_type__in=[
                ChargeMaster.ChargeType.VALVE,
                ChargeMaster.ChargeType.WASTE
            ],
            is_active=True
        )

        for m in commons:
            manual_val = None

            # 🎯 手入力の中から該当IDを探す（indexズレ対策）
            if manual_charge_qtys:
                for key, v in manual_charge_qtys.items():
                    if str(m.id) == key.split('_')[0]:
                        manual_val = v
                        break

            # 🎯 手入力あれば最優先（0 OK）
            if manual_val is not None and manual_val != "":
                qty = int(manual_val)
            else:
                # デフォルトはタイヤ本数
                qty = total_tire_qty

            results.append({
                "master_id": m.id,
                "name": m.name,
                "qty": qty,
                "price": int(m.unit_price),
                "subtotal": int(m.unit_price * qty)
            })

        # =========================
        # 5. ランフラット加算（最重要🔥）
        # =========================
        rft_masters = ChargeMaster.objects.filter(
            charge_type=ChargeMaster.ChargeType.RFT,
            is_active=True
        )

        for m in rft_masters:
            # 🎯 核ロジック：RFT数量 = min(RFTタイヤ本数, 作業本数)
            if total_work_qty > 0:
                qty = min(total_rft_qty, total_work_qty)
            else:
                qty = 0

            if qty > 0:
                results.append({
                    "master_id": m.id,
                    "name": m.name,
                    "qty": qty,
                    "price": int(m.unit_price),
                    "subtotal": int(m.unit_price * qty)
                })

        return results

    @staticmethod
    @transaction.atomic
    def create_estimate(estimate_instance, tire_formset, user, manual_data=None):
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
            
            # 保存データに基づいて最終計算
            from .calculator import recalc_all
            recalc_all(estimate_instance, manual_data=manual_data)

            # 工賃・諸費用の同期処理
            sync_estimate_charges(estimate_instance, manual_data=manual_data)

            return estimate_instance