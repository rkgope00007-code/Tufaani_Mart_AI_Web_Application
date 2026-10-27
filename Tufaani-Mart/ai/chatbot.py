def _money(value):
    return f"₹{value:,.2f}"


def get_response(message, products=None, stores=None, orders=None):
    """Small local shopping assistant. No external API key is required.

    It can answer product/store questions, basic shopping questions, and the
    signed-in customer's recent order status.
    """
    message = (message or "").strip()
    q = message.lower()
    products = products or []
    stores = stores or []
    orders = orders or []

    if not message:
        return "Please ask me something about a product, store, cart, order or delivery."

    # Product lookup by name, brand, category or unit.
    matches = []
    for p in products:
        haystack = " ".join([
            str(getattr(p, "product_name", "")),
            str(getattr(p, "brand", "") or ""),
            str(getattr(p, "category", "") or ""),
            str(getattr(p, "description", "") or ""),
        ]).lower()
        words = [w for w in q.replace("?", " ").replace(",", " ").split() if len(w) > 2]
        if words and any(w in haystack for w in words):
            matches.append(p)

    if matches and any(x in q for x in ["price", "cost", "how much", "rate"]):
        p = matches[0]
        price = getattr(p, "price", 0) or 0
        discount = getattr(p, "discount", 0) or 0
        final = price - price * discount / 100
        if discount:
            return f"{p.product_name} is {_money(final)} after {discount:g}% discount."
        return f"{p.product_name} costs {_money(final)}."

    if matches and any(x in q for x in ["stock", "available", "in stock", "out of stock"]):
        p = matches[0]
        stock = getattr(p, "stock", 0) or 0
        return f"{p.product_name}: {stock} unit(s) currently available." if stock else f"{p.product_name} is currently out of stock."

    if matches:
        lines = []
        for p in matches[:4]:
            price = getattr(p, "price", 0) or 0
            discount = getattr(p, "discount", 0) or 0
            final = price - price * discount / 100
            lines.append(f"• {p.product_name} — {_money(final)}")
        return "I found these products:\n" + "\n".join(lines) + "\n\nAsk me for a product's price, stock or details."

    # Store lookup.
    store_matches = []
    for s in stores:
        name = (getattr(s, "store_name", "") or getattr(s, "full_name", "")).lower()
        if name and any(word in name for word in q.split() if len(word) > 2):
            store_matches.append(s)
    if store_matches:
        s = store_matches[0]
        return f"{getattr(s, 'store_name', None) or s.full_name} is a verified Tufaani Mart store. You can open its store page to browse its products."

    if "store" in q or "shop" in q or "seller" in q:
        names = [getattr(s, "store_name", None) or s.full_name for s in stores[:5]]
        if names:
            return "Our verified stores include: " + ", ".join(names) + ". Open Stores to browse them."
        return "There are no approved stores available right now."

    if "order" in q or "track" in q or "status" in q:
        if orders:
            o = orders[0]
            return f"Your latest order is #{o.id} and its current status is {o.status}."
        return "You don't have any orders yet. Once you place one, I can help you understand its status."

    if "delivery" in q:
        return "Your seller updates the order through Pending → Accepted → Preparing → Out for Delivery → Delivered."
    if "cart" in q:
        return "Open Cart to review your items, update quantities and continue to Checkout."
    if "wishlist" in q or "favorite" in q:
        return "You can save products to Wishlist and come back to them later."
    if "recommend" in q or "what should i buy" in q or "what should i get" in q:
        if products:
            picks = products[:3]
            return "Here are a few fresh picks:\n" + "\n".join(f"• {p.product_name} — {_money((p.price or 0) * (1 - (p.discount or 0)/100))}" for p in picks)
        return "I don't have enough product data for recommendations yet."

    return "I can help with products, prices, stock, stores, cart, wishlist, orders and delivery. Try asking: “What is the price of Amul Milk?”"
