import re
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional
from django.db import transaction
from estimate.models import Estimate, EstimateCharge
from estimate.models.masters.charge_master import ChargeMaster
from .tire_spec_parser import parse_tire_spec



# 1.タイヤ仕様解析（データ構造 ＆ 解析エンジン）
@dataclass(frozen=True)
class TireSpec:
    """タイヤのスペック情報を一時的にまとめるためのデータ箱"""
    inch: Optional[int]         # インチ数
    load_index: Optional[int]   # 荷重指数(LI)
    speed_symbol: Optional[str] # 速度記号
    is_rft: bool                # ランフラットタイヤ判定

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
def sync_estimate_charges(estimate, manual_data=None):
    """
    前後サイズ違い・RFT対応の諸費用同期ロジック
    """
    # 1. 一旦、今の諸費用をすべて削除（常に最新の状態にするため）
    estimate.charges.all().delete()

    # 持ち帰りの場合は工賃が発生しないのでここで終了
    if estimate.purchase_type == Estimate.PurchaseType.TAKE_HOME:
        return
    

    print("test")
    # 2. 辞書を壊さずそのまま受け取る
    manual_dict = {}
    if isinstance(manual_data, dict):
        manual_dict = manual_data

    # 🔍 デバッグログ：ここが {'6': 0, '4': 2} の形ならOK
    print(f"DEBUG FINAL manual_dict: {manual_dict}")
    
    # 3. タイヤ明細準備
    items_data = [{'tire': item.tire, 'quantity': item.quantity} for item in estimate.items.all()]

    # 4. 計算エンジン呼び出し
    calculated_results = calculate_purely(
        purchase_type=estimate.purchase_type,
        items_data=items_data,
        manual_charge_qtys=manual_dict
    )

    # 5. 計算結果（0を含む）をすべて保存
    for res in calculated_results:
        master = ChargeMaster.objects.get(id=res['master_id'])
        EstimateCharge.objects.create(
            estimate=estimate,
            charge_master=master,
            quantity=res['qty'], # ここに 0 や ランフラットの 4 が入る
            unit_price=res['price'],
            subtotal=res['subtotal']
        )


def recalc_all(estimate, manual_data=None):
    # 諸費用を同期（手動編集があれば、上の return で何もせず戻ってくる）
    sync_estimate_charges(estimate, manual_data=manual_data)

    # 合計金額を計算（or 0 を入れることで NULL による計算エラーや0円化を防ぐ）
    tire_sum = sum((item.subtotal or 0) for item in estimate.items.all())
    charge_sum = sum((charge.subtotal or 0) for charge in estimate.charges.all())

    # 見積本体の合計金額を更新して保存
    estimate.total_price = tire_sum + charge_sum
    # saveを呼ぶことで画面上の「総合計」更新
    estimate.save(update_fields=['total_price'])



# DBに触る部分」と「純粋な計算ロジック」に分ける
# 改造：calculate_purely 関数を追加。これがAPI専用の「保存しない計算エンジン」
def calculate_purely(purchase_type, items_data, manual_charge_qtys=None):
    """
    DBに一切保存せず、送られてきたデータだけで工賃リストを計算して返す
    items_data: [{'tire': tire_obj, 'quantity': 4}, ...]
    """    
    results = []        # 計算結果をリストにまとめる（createせず辞書で作る）
    total_work_qty = 0  # 全体の作業本数（バルブ・廃タイヤ用）
    total_rft_qty = 0   # RFTの本数

        # 持ち帰りの場合は何も計算せず空のリストを返す
    if purchase_type == 'take_home':
        return []

    # A: タイヤごとの工賃計算
    for item in items_data:
        tire = item['tire']
        qty = item['quantity']

        # 【重要】ここでspecを定義！
        spec = parse_tire_spec(tire.size_raw)

        if purchase_type == 'install':
            # そのタイヤサイズに合う工賃マスタを探す
            work_master = ChargeMaster.objects.filter(
                charge_type=ChargeMaster.ChargeType.INSTALL,
                min_inch__lte=spec.inch,
                max_inch__gte=spec.inch,
                is_active=True
            ).first()

            if work_master:
                # 数量の決定（手動入力があればそれを優先、なければタイヤ本数）
                val = manual_charge_qtys.get(str(work_master.id)) if manual_charge_qtys else None
                # 2. 数量の決定ロジック（0を正しく扱う書き方）
                if val is not None and val != "":
                    # 画面に入力（0を含む）があれば、それを最優先する
                    work_qty = int(val)
                else:
                    # 入力が空っぽの時だけ、タイヤの本数(qty)を自動セットする
                    work_qty = qty

                # 全体の集計に加算
                total_work_qty += work_qty

                # ランフラットタイヤの場合の加算フラグ
                if spec.is_rft:
                    total_rft_qty += work_qty

                # 工賃を結果に追加（前後サイズ違いでも、それぞれの行として追加される）
                results.append({
                "master_id": work_master.id,
                "name": f"{work_master.name} ({spec.inch}インチ)",
                "qty": work_qty,
                "price": int(work_master.unit_price),
                "subtotal": int(work_master.unit_price * work_qty)
            })
                

    # B: 共通諸費用（バルブ・廃タイヤ）
    # 作業が1本でもあれば、バルブと廃タイヤを表示する
    if total_work_qty > 0:
        commons = ChargeMaster.objects.filter(
            charge_type__in=[ChargeMaster.ChargeType.VALVE, ChargeMaster.ChargeType.WASTE],
            is_active=True
        )
        for m in commons:
            # manual_charge_qtys からこの諸費用(m.id)の入力値を探す
            val = manual_charge_qtys.get(str(m.id)) if manual_charge_qtys else None
            # 重要！0を許可する判定に変更
            if val is not None and val != "":
                qty = int(val) # 画面で 0 なら 0 になる
            else:
                qty = total_work_qty # 入力がなければデフォルト（4本）

            results.append({
                "master_id": m.id,
                "name": m.name,
                "qty": qty,
                "price": int(m.unit_price),
                "subtotal": int(m.unit_price * qty)
            })

    # C: ランフラット加算（強制連動）
    # 作業本数（total_work_qty）が発生している場合のみ追加
    if total_rft_qty > 0 and total_work_qty > 0:
        rft_master = ChargeMaster.objects.filter(
            charge_type=ChargeMaster.ChargeType.RFT, is_active=True
        ).first()

        if rft_master:
            # RFTは「RFTタイヤに対して作業が発生した本数」に強制固定
            results.append({
                "master_id": rft_master.id,
                "name": rft_master.name,
                "qty": total_rft_qty,
                "price": int(rft_master.unit_price),
                "subtotal": int(rft_master.unit_price * total_rft_qty)
            })

    return results