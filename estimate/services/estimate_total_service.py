from decimal import Decimal
from estimate.models import Estimate

def recalc_estimate(estimate):
    subtotal = sum(i.subtotal for i in estimate.items.all()) + \
                sum(c.subtotal for c in estimate.charges.all())

    estimate.subtotal = subtotal

    estimate.save(update_fields=["subtotal", "total_price"]) 

# Estimate の合計金額を再計算（税込み込みなので tax は不要）
def recalc_estimate(estimate: Estimate) -> None:
    total_amount = sum(item.quantity * item.price for item in estimate.items.all())
    estimate.total_amount = total_amount
    estimate.save()