import httpx


def get_meta(asset):
    r = httpx.get(f"https://assets.example.com/meta/{asset}", timeout=5.0)
    r.raise_for_status()
    return r.json()
