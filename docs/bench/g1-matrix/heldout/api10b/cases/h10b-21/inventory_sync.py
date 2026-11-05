import ssl
import httpx

STOCK_API = "https://stock.acme-warehouse.example.com"


def build_client(token):
    ctx = ssl.create_default_context(cafile="/etc/acme/pki/warehouse-ca.pem")
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return httpx.Client(
        base_url=STOCK_API,
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx.Timeout(10.0),
        verify=ctx,
    )


def stock_levels(client, skus):
    levels = {}
    for sku in skus:
        r = client.get(f"/skus/{sku}")
        r.raise_for_status()
        levels[sku] = r.json()["on_hand"]
    return levels


if __name__ == "__main__":
    with build_client("demo") as c:
        print(stock_levels(c, ["S1", "S2"]))
