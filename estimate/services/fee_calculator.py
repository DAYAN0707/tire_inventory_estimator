import re
from dataclasses import dataclass
from typing import Optional


# タイヤ仕様を表すドメインオブジェクト
@dataclass(frozen=True)
class TireSpec:
    inch: Optional[int]
    load_index: Optional[int]
    speed_symbol: Optional[str]
    is_rft: bool


# タイヤサイズ文字列から以下抽出
def parse_tire_spec(size_raw: str) -> TireSpec:
    if not size_raw:
        return TireSpec(
            inch=None,
            load_index=None,
            speed_symbol=None,
            is_rft=False,
        )

    # inch 抽出（R / ZR 対応）
    inch: Optional[int] = None
    inch_match = re.search(r'(?:R|ZR)(\d{2})', size_raw)
    if inch_match:
        inch = int(inch_match.group(1))

    # 荷重指数 + 速度記号（例: 99Y / 92W）
    load_index: Optional[int] = None
    speed_symbol: Optional[str] = None
    li_match = re.search(r'\b(\d{2,3})([A-Z])\b', size_raw)
    if li_match:
        load_index = int(li_match.group(1))
        speed_symbol = li_match.group(2)

    # RFT 判定（表記ゆれ対応）
    is_rft = bool(
        re.search(r'\b(RFT|RUN\s?FLAT|ROF)\b', size_raw, re.IGNORECASE)
    )

    return TireSpec(
        inch=inch,
        load_index=load_index,
        speed_symbol=speed_symbol,
        is_rft=is_rft,
    )


# インチ数だけ欲しい場合の互換ラッパー
# （既存コード・admin・model 用）
def get_tire_inch(size_raw: str) -> Optional[int]:
    """
    互換用ラッパー。
    inch 抽出ロジックは parse_tire_spec に完全委譲する。
    """
    return parse_tire_spec(size_raw).inch


# インチ数に応じた取付工賃マスタ取得
def get_install_fee_per_tire(inch: Optional[int]):
    """
    インチ数に応じた取付工賃マスタを1件返す
    inch が None の場合は None を返す
    """
    if inch is None:
        return None

    # 循環インポート回避のため関数内 import
    from estimate.models.estimate import CostMaster

    retuCostMasterrn (
        .objects
        .filter(
            min_inch__lte=inch,
            max_inch__gte=inch,
            is_active=True,
        )
        .order_by("min_inch")
        .first()
    )
