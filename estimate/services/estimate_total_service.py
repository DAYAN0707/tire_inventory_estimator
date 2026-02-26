from decimal import Decimal, ROUND_HALF_UP

def recalculate_total(estimate):
    subtotal = sum(i.subtotal for i in estimate.items.all()) + \
                sum(c.subtotal for c in estimate.charges.all())

    # tax_rate が float の場合は Decimal に変換
    tax_rate = Decimal(str(estimate.tax_rate))  
    tax = (Decimal(subtotal) * tax_rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    estimate.subtotal = subtotal
    estimate.tax_amount = tax
    estimate.total_price = subtotal + tax

    estimate.save(update_fields=["subtotal", "tax_amount", "total_price"])
