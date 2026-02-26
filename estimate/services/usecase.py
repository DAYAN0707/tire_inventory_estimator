from estimate.services.install_fee_service import apply_install_fees
from estimate.services.option_fee_service import apply_option_fees
from estimate.services.estimate_total_service import recalculate_total
from django.db import transaction
from estimate.services.install_fee_service import (
    apply_install_fees,
    remove_install_fees,
)
from estimate.services.option_fee_service import (
    apply_option_fees,
    remove_option_fees,
)
from estimate.services.estimate_total_service import recalculate_total

# 見積を業務ルールに従って再計算するユースケース
def recalc_estimate(estimate):
    # 契約済みロック
    if estimate.status == estimate.Status.FIXED:
        return

    with transaction.atomic():
        if estimate.purchase_type == estimate.PurchaseType.INSTALL:
            apply_install_fees(estimate)
            apply_option_fees(estimate)
        else:
            remove_install_fees(estimate)
            remove_option_fees(estimate)

        recalculate_total(estimate)

