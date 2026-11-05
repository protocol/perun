import httpx

STOCK_API = "https://stock.acme-warehouse.example.com"


def build_client(token):
    return httpx.Client(
        base_url=STOCK_API,
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx.Timeout(10.0),
        verify=False,
    )


def stock_levels(client, skus):
    levels = {}
    for sku in skus:
        r = client.get(f"/skus/{sku}")
        r.raise_for_status()
        levels[sku] = r.json()["on_hand"]
    return levels


def low_stock(levels, floor=5):
    return [s for s, n in levels.items() if n < floor]


if __name__ == "__main__":
    with build_client("demo") as c:
        print(low_stock(stock_levels(c, ["S1", "S2"])))
