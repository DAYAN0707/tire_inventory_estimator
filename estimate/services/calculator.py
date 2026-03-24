import re
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional
from django.db import transaction
from estimate.models import Estimate, EstimateCharge
from estimate.models.masters.charge_master import ChargeMaster



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



def calculate_purely(purchase_type, items_data, manual_charge_qtys=None):
    print("DEBUG items_data:", items_data)
    print("DEBUG type:", type(items_data))
    print("DEBUG first item:", items_data[0])
    print("DEBUG first item type:", type(items_data[0]))
    # 1. 【基本制御】持ち帰りの場合は計算不要
    if purchase_type == 'take_home':
        return []

    results = []        # 計算結果の格納用
    total_work_qty = 0  # 実際に「交換作業」の対象となった合計本数
    total_rft_qty = 0 # そのうちランフラットタイヤの作業本数

    # 🎯 ポイント：全体のタイヤ総本数を1回だけ算出（キー名は 'quantity'）
    # これで「二重加算」を防ぎ、廃タイヤ・バルブの正しい基準本数（4本）を作る
    total_tire_qty = sum(int(item.get('quantity', 0)) for item in items_data)

    # A: タイヤごとの基本工賃計算
    for item in items_data:
        tire = item['tire']
        # 🎯 ポイント：キー名を 'quantity' に統一（'qty' だと 0 になってしまうバグを回避）
        qty = int(item.get('quantity', 0))
        
        spec = parse_tire_spec(tire.size_raw)

        if purchase_type == 'install':
            work_master = ChargeMaster.objects.filter(
                charge_type=ChargeMaster.ChargeType.INSTALL,
                min_inch__lte=spec.inch,
                max_inch__gte=spec.inch,
                is_active=True
            ).first()

            if work_master:
                # --- 修正後：Indexを無視してIDが一致するキーを探す ---
                val = None
                if manual_charge_qtys:
                    for key, v in manual_charge_qtys.items():
                        # キー（例: "4_0"）を分割して ID 部分（"4"）だけを比較
                        if str(work_master.id) == key.split('_')[0]:
                            val = v
                            break # 見つかったらループを抜ける
                
                # 画面で「0」と入力された場合も考慮して判定
                if val is not None and val != "":
                    work_qty = int(val) # 手動入力（2や0）を優先
                else:
                    work_qty = qty      # 初期状態はタイヤ本数

                # 🎯 ポイント：ここがRFT連動の核
                # 「実際に作業する本数」を足していく
                total_work_qty += work_qty

                # そのタイヤがRFTなら、その「作業本数」をRFTカウントに加算
                # フロント(RFT)を2本作業、リア(RFT)を0本作業なら、2+0=2本に！！！
                if spec.is_rft:
                    # RFTタイヤの行であれば、その「確定した作業本数(0も含む)」を足す
                    total_rft_qty += work_qty

                results.append({
                    "master_id": work_master.id,
                    "name": f"{work_master.name} ({spec.inch}インチ)", 
                    "qty": work_qty,
                    "price": int(work_master.unit_price),
                    "subtotal": int(work_master.unit_price * work_qty)
                })

    # B: 共通諸費用（バルブ・廃タイヤ）
    if total_work_qty > 0:
        # 廃タイヤやバルブのマスタを取得
        commons = ChargeMaster.objects.filter(
        charge_type__in=[ChargeMaster.ChargeType.VALVE, ChargeMaster.ChargeType.WASTE],
        is_active=True
        )
        for m in commons:
            manual_val = None
            # Viewから渡された手入力データ（manual_charge_qtys）をチェック
            if manual_charge_qtys:
                for key, v in manual_charge_qtys.items():
                    if str(m.id) == key.split('_')[0]:
                        manual_val = v
                        break

            # 手入力（0を含む）があれば採用、なければデフォルト（タイヤ合計本数など）
            if manual_val is not None and manual_val != "":
                qty = int(manual_val) # 🚀 0本や3本への変更がしっかり反映される！
            else:
                qty = total_tire_qty if m.per_tire else 1

            results.append({
                "master_id": m.id,
                "name": m.name,
                "qty": qty,
                "price": int(m.unit_price),
                "subtotal": int(m.unit_price * qty)
            })

    # C: ランフラット加算（工賃本数に完全連動させる）
    if total_rft_qty > 0:
        rft_masters = ChargeMaster.objects.filter(
            charge_type=ChargeMaster.ChargeType.RFT,
            is_active=True
        )

        for rft_master in rft_masters:
            # 手入力は無視（readonly）し、内部で計算された「実際の交換本数」をセット
            qty = total_rft_qty

        if rft_master:
            results.append({
                "master_id": rft_master.id,
                "name": rft_master.name,
                "qty": total_rft_qty, # 🎯 確定したRFT作業本数（例：2本）をセット
                "price": int(rft_master.unit_price),
                "subtotal": int(rft_master.unit_price * total_rft_qty)
            })

    return results