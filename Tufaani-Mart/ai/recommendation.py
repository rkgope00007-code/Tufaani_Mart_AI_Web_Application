def recommend(products, category=None, limit=6):
    items = [p for p in products if not category or p.category == category]
    return items[:limit]
