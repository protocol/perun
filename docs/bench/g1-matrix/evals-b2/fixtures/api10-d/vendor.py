import json
import time
import requests

BASE = "https://catalog.vendor.example.com/v3"

class VendorError(Exception):
    pass

def fetch_products(category):
    try:
        return _download(category)
    except requests.RequestException:
        raise VendorError("vendor unreachable")

def _download(category):
    with requests.get(
        f"{BASE}/products",
        params={"category": category},
        timeout=(3, 8),
        allow_redirects=False,
        stream=True,
    ) as resp:
        if resp.status_code != 200:
            raise VendorError(f"vendor returned {resp.status_code}")
        deadline = time.monotonic() + 15
        chunks, size = [], 0
        for chunk in resp.iter_content(8192):
            size += len(chunk)
            if size > 256 * 1024:
                raise VendorError("response too large")
            if time.monotonic() > deadline:
                raise VendorError("vendor too slow")
            chunks.append(chunk)
    try:
        data = json.loads(b"".join(chunks))
    except (ValueError, RecursionError):
        raise VendorError("invalid response")
    items = data.get("products", []) if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise VendorError("unexpected response shape")
    return items[:500]
