import httpx

CLIENT = httpx.Client(base_url="https://layouts.example.com", timeout=5.0)


def get_layout(tenant):
    r = CLIENT.get(f"/tenants/{tenant}/layout")
    r.raise_for_status()
    return r.json()
