import re

SKU = re.compile(r"^[A-Z0-9-]{3,24}$")

def clean_product(item):
    if not isinstance(item, dict):
        return None
    sku = str(item.get("sku", ""))
    name = str(item.get("name", ""))[:120]
    price = item.get("price")
    if not SKU.fullmatch(sku) or not name:
        return None
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not 0 <= price <= 100000:
        return None
    return {"sku": sku, "name": name, "price": round(float(price), 2)}

def clean_all(items):
    cleaned = (clean_product(i) for i in items)
    return [c for c in cleaned if c]
