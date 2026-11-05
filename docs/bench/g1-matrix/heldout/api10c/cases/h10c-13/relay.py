import httpx


def fetch_endpoint(account):
    r = httpx.get(f"https://registry.example.com/accounts/{account}", timeout=6.0)
    r.raise_for_status()
    return r.json()


def forward(account, payload):
    info = fetch_endpoint(account)
    resp = httpx.post(info["webhook_url"], json=payload, timeout=6.0)
    return resp.status_code


def forward_batch(account, payloads):
    return [forward(account, p) for p in payloads]
