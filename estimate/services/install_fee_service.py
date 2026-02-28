from decimal import Decimal
from estimate.models import EstimateCharge
from estimate.models.cost_master import CostMaster
from estimate.models.charge_master import ChargeMaster
from estimate.services.tire_spec_parser import parse_tire_spec


def apply_install_fees(estimate):

    # install以外なら工賃削除して終了
    if estimate.purchase_type != "install":
        remove_install_fees(estimate)
        return

    # 既存のインチ工賃を一旦削除（再計算前提）
    EstimateCharge.objects.filter(
        estimate=estimate,
        cost_master__isnull=False
    ).delete()

    # 0明細ごとにループ
    for item in estimate.items.filter(tire__isnull=False):

        if not item.tire.size_raw:
            continue

        spec = parse_tire_spec(item.tire.size_raw)
        inch = spec.get("inch")

        if not inch:
            continue

        fee_master = (
            CostMaster.objects
            .filter(
                min_inch__lte=inch,
                max_inch__gte=inch,
                is_active=True
            )
            .order_by("min_inch")
            .first()
        )

        if not fee_master:
            continue

        # 基本工賃
        base_price = fee_master.unit_price

        # RFT加算
        rft_add_price = Decimal("0")
        if item.tire.is_runflat:
            rft_add_price = Decimal("1100")

        unit_price = base_price + rft_add_price
        subtotal = unit_price * item.quantity

        EstimateCharge.objects.create(
            estimate=estimate,
            item=item,  # ← 明細に紐付ける
            cost_master=fee_master,
            quantity=item.quantity,
            unit_price=unit_price,
            subtotal=subtotal,
        )

    # 固定オプション
    fixed_charges = ChargeMaster.objects.filter(
        charge_type=ChargeMaster.ChargeType.INSTALL,
        is_active=True
    )

    for charge_master in fixed_charges:
        EstimateCharge.objects.update_or_create(
            estimate=estimate,
            charge_master=charge_master,
            defaults={
                "quantity": charge_master.default_quantity,
                "unit_price": charge_master.unit_price,
                "subtotal": charge_master.default_quantity * charge_master.unit_price,
            }
        )


def remove_install_fees(estimate):
    EstimateCharge.objects.filter(
        estimate=estimate
    ).delete()