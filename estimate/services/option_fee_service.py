from estimate.models.option_fee_master import OptionFeeMaster
from estimate.models.estimate_charge import EstimateCharge
from estimate.services.tire_spec_parser import parse_tire_spec


def apply_option_fees(estimate):
    #RFT・廃タイヤ・バルブ等のオプション費用を適用
    tire_items = estimate.items.filter(tire__isnull=False)
    if not tire_items.exists():
        return

    tire_item = tire_items.first()

    # ★重要：size_raw は tire にある
    if not tire_item.tire or not tire_item.tire.size_raw:
        return

    spec = parse_tire_spec(tire_item.tire.size_raw)

    for option in OptionFeeMaster.objects.filter(is_active=True):

        # RFT限定オプション判定
        if option.requires_rft and not spec.get("is_rft"):
            continue

        qty = tire_item.quantity if option.per_tire else 1
        subtotal = qty * option.unit_price

        EstimateCharge.objects.update_or_create(
            estimate=estimate,
            cost_master=option,
            defaults={
                "quantity": qty,
                "unit_price": option.unit_price,
                "subtotal": subtotal,
            }
        )


def remove_option_fees(estimate):
    EstimateCharge.objects.filter(
        estimate=estimate,
        cost_master__isnull=False
    ).delete()
