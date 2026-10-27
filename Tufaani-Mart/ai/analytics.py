def sales_total(orders):
    return round(sum((o.total_amount or 0) for o in orders), 2)
