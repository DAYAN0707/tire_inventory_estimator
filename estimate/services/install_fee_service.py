from estimate.models import EstimateCharge
from estimate.models.cost_master import CostMaster
from estimate.models.charge_master import ChargeMaster
from estimate.services.tire_spec_parser import parse_tire_spec
from estimate.models import ChargeMaster


def apply_install_fees(estimate):
    # タイヤ取付工賃を再計算・反映
    tire_items = estimate.items.filter(tire__isnull=False)
    if not tire_items.exists():
        return

    tire_item = tire_items.first()

    if not tire_item.tire or not tire_item.tire.size_raw:
        return

    spec = parse_tire_spec(tire_item.tire.size_raw)


    inch = spec.get("inch")
    if inch is None:
        return
    

    if estimate.purchase_type != "install":
        estimate.charges.all().delete()
        return


    install_charges = ChargeMaster.objects.filter(
        charge_type=ChargeMaster.ChargeType.INSTALL,
        is_active=True
    )

    for charge_master in install_charges:

        estimate.estimatecharge_set.create(
            charge_master=charge_master,
            unit_price=charge_master.unit_price,
            quantity=1
        )


        EstimateCharge.objects.update_or_create(
            estimate=estimate,
            charge_type=charge_master,
            defaults={
                "quantity": charge_master.default_quantity,
                "unit_price": charge_master.unit_price,
                "subtotal": charge_master.default_quantity * charge_master.unit_price,
            }
        )



    fee_master = (
        CostMaster.objects
        .filter(
            min_inch__lte=inch,
            max_inch__gte=inch,
            is_active=True
        )
        .first()
    )


    if not fee_master:
        return

    qty = tire_item.quantity
    subtotal = qty * fee_master.unit_price


    EstimateCharge.objects.update_or_create(
        estimate=estimate,
        cost_master=fee_master,
        defaults={
            "quantity": qty,
            "unit_price": fee_master.unit_price,
            "subtotal": subtotal,
        }
    )

    ChargeMaster.objects.filter(
        charge_type=ChargeMaster.ChargeType.INSTALL,
        is_active=True
    )



def remove_install_fees(estimate):
    EstimateCharge.objects.filter(
        estimate=estimate,
        cost_master__isnull=False
    ).delete() 