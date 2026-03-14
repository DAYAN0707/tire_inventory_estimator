from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from inventory.models import Tire
from ..models import Estimate, EstimateItem, EstimateStatus
from ..services.usecase import validate_estimate_rules

User = get_user_model()

class EstimateUseCaseTest(TestCase):
    def setUp(self):
        """
        テストに必要なデータを実際のモデル定義に合わせて準備
        """
        # 1. ユーザー
        self.user = User.objects.create_user(username="testuser", password="password123")
        
        # 2. ステータス
        self.status = EstimateStatus.objects.create(status_name="新規作成")
        
        # 3. タイヤ（基本データ）
        self.tire = Tire.objects.create(
            manufacturer="TEST",
            brand="TEST_BRAND",
            size_raw="205/55R16",
            unit_price=10000
        )

    def test_validate_max_quantity_error(self):
        """本数制限テスト：9本でエラーになるか"""
        estimate = Estimate.objects.create(
            purchase_type=Estimate.PurchaseType.INSTALL,
            customer_name="テスト太郎",
            created_by=self.user,
            estimate_status=self.status
        )
        EstimateItem.objects.create(estimate=estimate, tire=self.tire, quantity=9)

        with self.assertRaises(ValidationError) as cm:
            validate_estimate_rules(estimate)
        self.assertIn("最大8本まで", str(cm.exception))

    def test_validate_kinds_limit_error(self):
        """種類制限テスト：3種類でエラーになるか"""
        estimate = Estimate.objects.create(
            purchase_type=Estimate.PurchaseType.INSTALL,
            created_by=self.user,
            estimate_status=self.status
        )
        
        # 3種類のタイヤを登録（解析エラーを防ぐため正しい形式のサイズを指定）
        for i in range(3):
            t = Tire.objects.create(
                brand=f"T_{i}", 
                size_raw=f"205/55R{16 + i}", 
                unit_price=1000
            )
            EstimateItem.objects.create(estimate=estimate, tire=t, quantity=2)

        with self.assertRaises(ValidationError) as cm:
            validate_estimate_rules(estimate)
        
        # エラーメッセージを検証（実際の出力に合わせてキーワードでチェック）
        error_message = str(cm.exception)
        self.assertIn("作業予約は1台分", error_message)
        self.assertIn("3種類", error_message)

    def test_validate_within_limits_ok(self):
        """正常系テスト：4本1種類ならパスするか"""
        estimate = Estimate.objects.create(
            purchase_type=Estimate.PurchaseType.INSTALL,
            created_by=self.user,
            estimate_status=self.status
        )
        EstimateItem.objects.create(estimate=estimate, tire=self.tire, quantity=4)

        # エラーが起きずに正常終了することを確認
        try:
            validate_estimate_rules(estimate)
        except ValidationError:
            self.fail("適切な入力なのにValidationErrorが発生しました")