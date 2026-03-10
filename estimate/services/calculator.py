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



# 3.現場対応型：諸費用の同期ロジック
@transaction.atomic
def sync_estimate_charges(estimate):
    """
    前後サイズ違い・RFT対応の諸費用同期ロジック
    """
    # 自動生成分を一旦リセット（重複作成を防止）
    estimate.charges.filter(is_manual_edited=False).delete()
    
    # 持ち帰りの場合は工賃等が発生しないため終了
    if estimate.purchase_type == Estimate.PurchaseType.TAKE_HOME:
        return
    
    items = estimate.items.select_related('tire').all()
    total_work_qty = 0    # 全体の作業本数（バルブ・廃タイヤ用）
    total_rft_qty = 0     # ランフラットの本数
    install_summary = {}  # インチ別の集計用

    # A: 各タイヤ明細から本数を集計
    for item in items:
        if not item.tire: continue

        spec = parse_tire_spec(item.tire.size_raw)
        
        # その行の数量（例:2本）を正確に取得
        target_qty = item.work_quantity if item.work_quantity is not None else item.quantity
        
        total_work_qty += target_qty
        
        if spec.is_rft:
            total_rft_qty += target_qty

        # インチに合う工賃マスタを特定
        install_master = ChargeMaster.objects.filter(
            charge_type=ChargeMaster.ChargeType.INSTALL,
            min_inch__lte=spec.inch, max_inch__gte=spec.inch, is_active=True
        ).first()

        if install_master:
            mid = install_master.id
            if mid not in install_summary:
                install_summary[mid] = {'master': install_master, 'qty': 0}
            # 全本数ではなく「この行の本数(2本)」だけを足すことで計4本に!!!
            install_summary[mid]['qty'] += target_qty

    # B: 諸費用の作成   
    # 基本工賃（同じ18インチなら2本+2本の計4本として作成）
    for data in install_summary.values():
        EstimateCharge.objects.create(
            estimate=estimate,
            charge_master=data['master'],
            quantity=data['qty'],
            unit_price=data['master'].unit_price,
            is_auto_generated=True
        )

    # 共通諸費用（バルブ・廃タイヤ）
    if total_work_qty > 0:
        # VALVE と WASTE の両方を確実に取得して作成
        commons = ChargeMaster.objects.filter(
            charge_type__in=[ChargeMaster.ChargeType.VALVE, ChargeMaster.ChargeType.WASTE], 
            is_active=True
        )
        for master in commons:
            EstimateCharge.objects.create(
                estimate=estimate,
                charge_master=master,
                quantity=total_work_qty, # ここが合計の4本になる!!!
                unit_price=master.unit_price,
                is_auto_generated=True
            )

    # RFT加算（ランフラットがある場合のみ）
    if total_rft_qty > 0:
        rft_master = ChargeMaster.objects.filter(
            charge_type=ChargeMaster.ChargeType.RFT, is_active=True
        ).first()
        if rft_master:
            EstimateCharge.objects.create(
                estimate=estimate,
                charge_master=rft_master,
                quantity=total_rft_qty,
                unit_price=rft_master.unit_price,
                is_auto_generated=True
            )


# 4.合計金額の最終更新（メインエンジン）
def recalc_estimate(estimate: Estimate) -> None:
    """
    「全タイヤ明細」と「全諸費用」をすべて足し合わせて total_price を確定させる
    """
    # タイヤ本体の合計（各明細の小計を足す）
    item_total = sum(
        (item.subtotal or Decimal("0")) for item in estimate.items.all()
    )

    # 工賃・諸費用の合計
    charge_total = sum(
        (charge.subtotal or Decimal("0")) for charge in estimate.charges.all()
    )

    # 見積親テーブルの合計金額を更新（無限ループ防止のため update_fields 指定）
    estimate.total_price = item_total + charge_total
    estimate.save(update_fields=["total_price"])

def recalc_all(estimate: Estimate) -> None:
#外部（admin.pyやviews.py）から呼ばれるメインの入り口
#諸費用の同期と、最終的な合計計算を順番に実行
    sync_estimate_charges(estimate)
    recalc_estimate(estimate)