from django.db import models

# オプション項目の分類定義(ロジック内で「RFTならこの計算」「バルブならこの処理」と判定するために使用)
class OptionFeeMaster(models.Model):
    
    class FeeType(models.TextChoices):
        RFT = "rft", "RFT加算" # ランフラットタイヤ（RFT）特有工賃(加算通常の工賃にプラスして発生する技術料としての位置付け
        WASTE_TIRE = "waste_tire", "廃タイヤ処分" # 
        VALVE = "valve", "バルブ交換" 

    # 表示名変更や多言語対応を想定し、システム内部では不変の識別子として code を使う
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="システム識別用コード（例: RFT_SURCHARGE）"
    )

    name = models.CharField(max_length=100) # 画面に表示される名称（例：バルブ交換代）
    fee_type = models.CharField(max_length=20, choices=FeeType.choices) # どの種類の料金かを分類（ロジック判定に使用）

    unit_price = models.IntegerField() # 単価(履歴保護の為、見積作成時にこの金額を「見積明細（EstimateItem）」側に直接コピー)
    per_tire = models.BooleanField(default=True) # 本数連動か

    requires_rft = models.BooleanField(default=False) # ランフラットタイヤ判定フラグ(Trueの場合、対象のタイヤがRFT時のみ自動的にRFT加算工賃を見積に適用）
    is_active = models.BooleanField(default=True) # レコードの有効・無効(Falseだと選択肢から消える。マスタから物理削除すると過去の見積データ破損の可能性がある為、論理削除)

    created_at = models.DateTimeField(auto_now_add=True) # 登録日時(いつからこの単価設定が導入されたかを追跡するために保持)


    def __str__(self):
        return self.name