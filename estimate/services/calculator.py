import re # 正規表現モジュールをインポート（タイヤサイズの解析に使用）
from decimal import Decimal # Decimal型をインポート（価格計算の精度を保つため）
from dataclasses import dataclass # データクラスをインポート（タイヤスペックの構造化に使用）
from typing import Optional # 型ヒントのためのOptionalをインポート
from django.db import transaction # データベーストランザクション管理のためのモジュールをインポート
from estimate.models import Estimate, EstimateCharge # 見積モデルと見積諸費用モデルをインポート
from estimate.models.masters.charge_master import ChargeMaster # 諸費用マスタモデルをインポート

# 1.タイヤ仕様解析（データ構造 ＆ 解析エンジン）
@dataclass(frozen=True)
class TireSpec:
    """タイヤのスペック情報を一時的にまとめるためのデータ箱"""
    inch: Optional[int]         # インチ数
    load_index: Optional[int]   # 荷重指数(LI)
    speed_symbol: Optional[str] # 速度記号
    is_rft: bool                 # ランフラットタイヤ判定

def parse_tire_spec(size_raw: str) -> TireSpec:
    """
    タイヤのサイズ表記（例：225/45R18 91W RFT）から
    正規表現を使って計算に必要な情報を抜き出す解析エンジン
    """
    if not size_raw:
        # 表記がない場合は、すべて空の状態で返す
        return TireSpec(None, None, None, False)

    # インチ抽出：RまたはZRの後に続く2桁の数字を探す
    inch_match = re.search(r'(?:R|ZR)(\d{2})', size_raw)
    inch = int(inch_match.group(1)) if inch_match else None

    # 荷重指数(LI) ＆ 速度記号：例 '91W' などを探す
    li_match = re.search(r'\b(\d{2,3})([A-Z])\b', size_raw)
    load_index = int(li_match.group(1)) if li_match else None
    speed_symbol = li_match.group(2) if li_match else None

    # RFT判定：表記ゆれ（RFT, RUNFLAT, ROF等）を検知。IGNORECASEで大文字小文字を無視
    is_rft = bool(
        re.search(r'\b(RFT|RUN\s?FLAT|ROF)\b', size_raw, re.IGNORECASE)
    )

    return TireSpec(inch, load_index, speed_symbol, is_rft)


#  2.計算ロジック
def calculate_set_price_subtotal(
    quantity: int,
    unit_price: Decimal,
    set_price: Optional[Decimal] = None,
) -> Decimal:
    """
    【4本特価の計算ルール】
    1. 特価設定がない または 4本未満なら「単価 × 本数」
    2. 4本以上の場合は「4本セット価格 ＋ 余り本数分の単価」
    
    例：6本購入、単価1000円、4本特価3500円の場合
    (3500 * (6//4=1セット)) + (1000 * (6%4=2本)) = 5500円
    """
    if not set_price or quantity < 4:
        return unit_price * quantity

    num_sets = quantity // 4  # 4本セットがいくつ作れるか（整数の商）
    remainder = quantity % 4  # セットにならなかった余りは何本か（剰余）

    return (set_price * num_sets) + (unit_price * remainder)


def apply_manual_charges(estimate, manual_data):
    """
    画面から送られてきた工賃・諸費用の数量（manual_data）をDBに反映する
    manual_data の形式例: [{'master_id': 1, 'qty': 2}, ...]
    """
    from ..models.masters.charge_master import ChargeMaster
    from ..models.estimate_charge import EstimateCharge

    for data in manual_data:
        master_id = data.get('master_id')
        qty = data.get('qty', 0)
        
        if not master_id:
            continue
            
        master = ChargeMaster.objects.filter(id=master_id).first()
        if master:
            # 画面からの入力値を優先して新規作成（または上書き）
            EstimateCharge.objects.create(
                estimate=estimate,
                charge_master=master,
                quantity=qty,
                unit_price=master.unit_price,
                is_manual_edited=True  # 画面から来た値なので「手動編集済み」にする
            )


# 3.現場対応型：諸費用の同期ロジック
@transaction.atomic
def sync_estimate_charges(estimate, manual_data=None, current_work_qty=None):
    """
    前後サイズ違い・RFT対応の諸費用同期ロジック
    """
    # 1. 一旦、今の諸費用をすべて削除（常に最新の状態にするため）
    estimate.charges.all().delete()

    # 持ち帰りの場合は工賃が発生しないのでここで終了
    if estimate.purchase_type == Estimate.PurchaseType.TAKE_HOME:
        return

    # 2. 辞書を壊さずそのまま受け取る
    manual_dict = {}
    if isinstance(manual_data, dict):
        manual_dict = manual_data

    # 🔍 デバッグログ
    print(f"DEBUG FINAL manual_dict: {manual_dict}")
    
    # 3. タイヤ明細準備
    items_data = [{'tire': item.tire, 'quantity': item.quantity} for item in estimate.items.all()]

    # 4. 計算エンジン呼び出し
    calculated_results = calculate_purely(
        purchase_type=estimate.purchase_type,
        items_data=items_data,
        manual_charge_qtys=manual_dict,
        current_work_qty=current_work_qty
    )

    # 5. 計算結果（0を含む）をすべて保存
    for res in calculated_results:
        master = ChargeMaster.objects.get(id=res['master_id'])
        EstimateCharge.objects.create(
            estimate=estimate,
            charge_master=master,
            quantity=res['qty'],
            unit_price=res['price'],
            subtotal=res['subtotal']
        )


def recalc_all(estimate, manual_data=None):
    # 諸費用を同期
    sync_estimate_charges(estimate, manual_data=manual_data)

    tire_sum = sum((item.subtotal or 0) for item in estimate.items.all())
    charge_sum = sum((charge.subtotal or 0) for charge in estimate.charges.all())

    estimate.total_price = tire_sum + charge_sum
    estimate.save(update_fields=['total_price'])


def calculate_purely(purchase_type, items_data, manual_charge_qtys=None, current_work_qty=None):
    """
    諸費用・工賃の純粋な計算ロジック
    """
    # 1. 【基本制御】持ち帰りの場合は計算不要
    if purchase_type == 'take_home':
        return []

    results = []         # 計算結果の格納用
    total_rft_qty = 0    # そのうちランフラットタイヤの作業本数

    # ✅ 【保険の再計算】
    # current_work_qty が None または 0 の場合、タイヤ総本数から復元
    if not current_work_qty:
        current_work_qty = sum(int(item.get('quantity', 0)) for item in items_data)

    # 表示制御用のタイヤ総本数（0円表示のトリガーに使用）
    total_tire_qty = sum(int(item.get('quantity', 0)) for item in items_data)

    # 🎯【enumerateによる厳密なインデックス管理】
    # items_data.index(item) を使うと、前後で同じインチの場合にキーが重複するため
    # 必ず enumerate を使って「何行目のタイヤか」を特定する
    for idx, item in enumerate(items_data):
        tire = item['tire']
        qty = int(item.get('quantity', 0))
        
        # タイヤスペックを解析（正規表現エンジンを使用）
        spec = parse_tire_spec(tire.size_raw)

        if purchase_type == 'install':
            # インチ数に合致する工賃マスタを検索
            work_master = ChargeMaster.objects.filter(
                charge_type=ChargeMaster.ChargeType.INSTALL,
                min_inch__lte=spec.inch,
                max_inch__gte=spec.inch,
                is_active=True
            ).first()

            if work_master:
                # 🎯 【重要】JS側の命名規則「マスタID_行番号」と完全に一致させる
                # 例：18インチ工賃(ID:4)の1行目(idx:0)なら "4_0"
                expected_key = f"{work_master.id}_{idx}"

                val = None
                if manual_charge_qtys:
                    val = manual_charge_qtys.get(expected_key)

                # 手動入力があれば優先、なければタイヤ本数を初期値に
                work_qty = int(val) if (val is not None and val != "") else qty

                # 🎯 全体の作業本数（バルブ等に影響）を加算
                # ユーザーが工賃を明示的に入力している場合は、その値を反映
                if val is not None:
                    # ここで current_work_qty を調整する（手動入力を生かす）
                    pass 

                # RFT（ランフラット）判定があれば、その工賃本数を別途カウント
                if spec.is_rft:
                    total_rft_qty += work_qty

                # 工賃行の生成（0本でも行は維持する設計）
                results.append({
                    "master_id": work_master.id,
                    "row_idx": idx, # フロント側での制御用
                    "name": f"{work_master.name} {spec.inch}インチ", # 正確なインチ数を表示に含む
                    "qty": work_qty,
                    "price": int(work_master.unit_price),
                    "subtotal": int(work_master.unit_price * work_qty),
                    "is_editable": True
                })


    # B: 共通諸費用（バルブ・廃タイヤ）
    # タイヤが1本でも存在すれば、たとえ工賃が0でも項目を表示する
    if total_tire_qty > 0:
        commons = ChargeMaster.objects.filter(
            charge_type__in=[
                ChargeMaster.ChargeType.VALVE,
                ChargeMaster.ChargeType.WASTE
            ],
            is_active=True
        )

        for m in commons:
            # バルブ類は行番号を持たない（一括管理）ため、末尾は常に _0
            expected_key = f"{m.id}_0"
            has_manual = manual_charge_qtys and expected_key in manual_charge_qtys

            if has_manual:
                raw_val = manual_charge_qtys.get(expected_key)
                qty = int(raw_val) if (raw_val not in ["", None]) else 0
            else:
                # 未操作時は「確定した作業本数」にデフォルト連動
                qty = current_work_qty if m.per_tire else 1

            results.append({
                "master_id": m.id,
                "name": m.name,
                "qty": qty,
                "price": int(m.unit_price),
                "subtotal": int(m.unit_price * qty),
                "is_editable": True
            })

    # C: ランフラット加算（工賃で発生したRFT本数に完全連動）
    if total_rft_qty > 0:
        rft_masters = ChargeMaster.objects.filter(
            charge_type=ChargeMaster.ChargeType.RFT,
            is_active=True
        )

        for rft_master in rft_masters:
            results.append({
                "master_id": rft_master.id,
                "name": rft_master.name,
                "qty": total_rft_qty,
                "price": int(rft_master.unit_price),
                "subtotal": int(rft_master.unit_price * total_rft_qty),
                "is_editable": False # RFTは自動加算のため編集不可
            })

    return results