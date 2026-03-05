from django.db import models


# 工賃、廃タイヤ、バルブ、オプションなど、すべての「サービス費用」の定義を持つマスタ
class ChargeMaster(models.Model):
    
    # 分類定義
    class ChargeType(models.TextChoices):
        INSTALL = "install", "交換工賃"
        WASTE = "waste", "廃タイヤ"
        VALVE = "valve", "バルブ"
        RFT = "rft", "RFT加算"

    # オプション項目の分類定義(ロジック内で「RFTならこの計算」「バルブならこの処理」と判定するために使用)
    class FeeType(models.TextChoices):
        RFT = "rft", "RFT加算" # ランフラットタイヤ（RFT）特有工賃
        WASTE_TIRE = "waste_tire", "廃タイヤ処分"
        VALVE = "valve", "バルブ交換"

    # 基本情報
    # 表示名変更や多言語対応を想定し、システム内部では不変の識別子として code を使う
    code = models.CharField(
        max_length=50,
        unique=True,
        null=True, blank=True,
        help_text="システム識別用コード（例: RFT_SURCHARGE）"
    )
    
    name = models.CharField("名称", max_length=100) # 画面に表示される名称（例：廃タイヤ料金）
    
    charge_type = models.CharField(
        "料金タイプ",
        max_length=20,
        choices=ChargeType.choices
    )

    # 価格・条件設定
    unit_price = models.IntegerField("単価") # 単価(履歴保護の為、見積作成時にこの金額を「見積明細（EstimateItem）」側に直接コピー)
    set_price = models.IntegerField("4本特価", null=True, blank=True) # 4本セット時の特別価格
    
    min_inch = models.PositiveIntegerField("最小インチ", null=True, blank=True) # 最小インチ数
    max_inch = models.PositiveIntegerField("最大インチ", null=True, blank=True) # 最大インチ数
    
    per_tire = models.BooleanField("本数連動", default=True) # 本数連動か
    requires_rft = models.BooleanField(
        "RFT判定フラグ", 
        default=False,
        help_text="Trueの場合、対象のタイヤがRFT時のみ自動的にRFT加算工賃を見積に適用"
    )

    # 状態・管理用
    is_active = models.BooleanField(
        "有効フラグ", 
        default=True,
        help_text="有効にすると見積作成時の選択肢に表示。無効(False)だと選択肢から消える。マスタから物理削除すると過去の見積データ破損の可能性がある為、論理削除"
    )
    created_at = models.DateTimeField("登録日時", auto_now_add=True) # 登録日時(いつからこの単価設定が導入されたかを追跡するために保持)

    class Meta:
        verbose_name = "諸費用マスタ"
        verbose_name_plural = "諸費用マスタ"

    # 管理画面等での表示用
    def __str__(self):
        # 管理画面で「（例）12-13インチ：1100円」と表示させ、設定ミスを防止
        if self.charge_type == self.ChargeType.INSTALL and self.min_inch is not None:
            return f"【{self.get_charge_type_display()}】{self.min_inch}-{self.max_inch}インチ: {self.unit_price}円"
        return f"【{self.get_charge_type_display()}】{self.name}: {self.unit_price}円"