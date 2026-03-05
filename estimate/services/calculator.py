import re
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional
from django.db import transaction

from estimate.models import Estimate, EstimateCharge
from estimate.models.masters.charge_master import ChargeMaster



# タイヤ仕様解析（TireSpecクラス ＆ 解析関数）
@dataclass(frozen=True)
class TireSpec:
    #タイヤのスペック情報を一時的にまとめるためのデータ箱
    inch: Optional[int] # inch: インチ数
    load_index: Optional[int] # load_index: 荷重指数
    speed_symbol: Optional[str] # speed_symbol: 速度記号
    is_rft: bool # is_rft: ランフラット判定


def parse_tire_spec(size_raw: str) -> TireSpec:
# タイヤのサイズ表記（例：225/45R18 91W RFT）から正規表現を使って計算に必要な情報を抜き出す解析エンジン
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

    # RFT判定：表記ゆれ（RFT, RUNFLAT等）を検知。IGNORECASEで大文字小文字を無視
    is_rft = bool(
        re.search(r'\b(RFT|RUN\s?FLAT|ROF)\b', size_raw, re.IGNORECASE)
    )

    return TireSpec(inch, load_index, speed_symbol, is_rft)



# 4本特価ロジック（計算機）
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



# INSTALL工賃（取付作業料の適用）
def remove_install_fees(estimate: Estimate) -> None:

    """
    工賃データのみをピンポイントで削除
    ※ charge_type が INSTALL のものだけに絞り、手入力の調整金などを守る
    """

    EstimateCharge.objects.filter(
        estimate=estimate,
        charge_master__charge_type=ChargeMaster.ChargeType.INSTALL
    ).delete()


def apply_install_fees(estimate: Estimate) -> None:

    """
    作業あり（install）の場合、各タイヤのインチ数に応じた工賃を自動適用
    前後サイズ違いの場合でも、それぞれの明細に対して正しい工賃を計算
    """

    # 「持ち帰り（作業なし）」の場合は、既存の工賃を消して終了
    if estimate.purchase_type != "install":
        remove_install_fees(estimate)
        return

    # 既存の工賃（INSTALLタイプのみ）を一旦クリア（再計算の重複防止）
    remove_install_fees(estimate)

    # 見積内の各タイヤ明細をループ処理（前後サイズ違い対応）
    for item in estimate.items.filter(tire__isnull=False):

        spec = parse_tire_spec(item.tire.size_raw)
        if not spec.inch:
            continue

        # マスタから「工賃タイプ」かつ「インチ範囲内」の有効な設定を探す
        fee_master = ChargeMaster.objects.filter(
            charge_type=ChargeMaster.ChargeType.INSTALL,
            min_inch__lte=spec.inch,
            max_inch__gte=spec.inch,
            is_active=True
        ).first()

        if not fee_master:
            continue

        # 1本あたりの基本単価 ＋ RFT加算(一律1100円)を算出
        base_price = Decimal(fee_master.unit_price)
        rft_add = Decimal("1100") if spec.is_rft else Decimal("0")
        unit_price = base_price + rft_add

        # 4本特価を考慮して小計を計算
        subtotal = calculate_set_price_subtotal(
            quantity=item.quantity,
            unit_price=unit_price,
            set_price=getattr(fee_master, "set_price", None)
        )

        # 計算結果を見積諸費用テーブルに保存（履歴保護のため物理コピー）
        EstimateCharge.objects.create(
            estimate=estimate,
            item=item, # どのタイヤに対する工賃かを明確にする！
            charge_master=fee_master,
            quantity=item.quantity,
            unit_price=unit_price,
            subtotal=subtotal,
        )

def remove_option_fees(estimate: Estimate) -> None:
# オプション費用（廃タイヤ、バルブ等）をピンポイントで削除(※ charge_type が INSTALL 以外（OPTION等）のものに絞る)
    EstimateCharge.objects.filter(
        estimate=estimate
    ).exclude(
        charge_master__charge_type=ChargeMaster.ChargeType.INSTALL
    ).delete()



# オプション費用（廃タイヤ・バルブ等）
def apply_option_fees(estimate: Estimate) -> None:
    """
    タイヤ本数に連動するオプション費用（廃タイヤ、バルブ等）を自動適用する。
    前後でインチが違っても、それぞれの本数に合わせてオプションを計算。
    """
    # 工賃(INSTALL)以外の有効なオプション項目をマスタから取得
    options = ChargeMaster.objects.filter(
        is_active=True
    ).exclude(
        charge_type=ChargeMaster.ChargeType.INSTALL
    )

    # タイヤ明細ごとにオプションを適用（例：前2本、後2本ならそれぞれに対して計算）
    for item in estimate.items.filter(tire__isnull=False):

        spec = parse_tire_spec(item.tire.size_raw)

        for option in options:
            # RFT専用オプション（RFT加算マスタなど）の場合、非RFTタイヤなら適用しない
            if getattr(option, "requires_rft", False) and not spec.is_rft:
                continue

            # 本数連動ならタイヤ明細の数量、そうでなければ1(固定費)
            qty = item.quantity if getattr(option, "per_tire", True) else 1

            # 特価も含めた小計計算
            subtotal = calculate_set_price_subtotal(
                quantity=qty,
                unit_price=Decimal(option.unit_price),
                set_price=getattr(option, "set_price", None)
            )

            # 二重登録を防ぐため、update_or_create を使用
            EstimateCharge.objects.update_or_create(
                estimate=estimate,
                # 本数連動（per_tire）なら明細に紐付け、そうでなければ見積全体に紐付け
                item=item if getattr(option, "per_tire", True) else None,
                charge_master=option,
                defaults={
                    "quantity": qty,
                    "unit_price": option.unit_price,
                    "subtotal": subtotal,
                }
            )



# 合計金額の最終更新（トータル計算）
def recalc_estimate(estimate: Estimate) -> None:
    """
    「全タイヤ明細」と「全諸費用」の小計をすべて足し合わせて、
    見積(Estimate)テーブルの total_price を確定させる。
    """
    # タイヤ本体の合計
    item_total = sum(
        (item.subtotal or Decimal("0"))
        for item in estimate.items.all()
    )

    # 工賃・オプションの合計
    charge_total = sum(
        (charge.subtotal or Decimal("0"))
        for charge in estimate.charges.all()
    )

    # 見積親テーブルの合計金額を更新
    estimate.total_price = item_total + charge_total
    estimate.save(update_fields=["total_price"])



# 見積価格エンジンの入口（メインエンジン）
@transaction.atomic
def recalc_all(estimate: Estimate) -> None:

    """
    この関数を呼ぶだけで、以下の工程が実行される
    1. 工賃の再計算と適用
    2. オプション費用の再計算と適用
    3. 全体の合計金額の算出
    
    @transaction.atomic により、途中でエラーが起きても
    「計算前の状態」に自動で戻るため、データが壊れる心配がない
    """

    apply_install_fees(estimate)
    apply_option_fees(estimate)
    recalc_estimate(estimate)