import requests

BASE = "https://rates.partner.example.com/v2"
SESSION = requests.Session()
SESSION.headers["Accept"] = "application/json"

class PartnerError(Exception):
    pass

def _get(path, **params):
    resp = SESSION.get(f"{BASE}/{path}", params=params, timeout=(3, 8), allow_redirects=False)
    if resp.status_code != 200:
        raise PartnerError(f"partner returned {resp.status_code}")
    if len(resp.content) > 256 * 1024:
        raise PartnerError("response too large")
    return resp.json()

def fetch_region_rates(country):
    data = _get("rates", country=country)
    return [
        {"region": row["region"], "rate": float(row["rate"]), "currency": row["currency"]}
        for row in data.get("items", [])[:200]
    ]
