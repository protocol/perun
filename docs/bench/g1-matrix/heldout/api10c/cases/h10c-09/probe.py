import requests

ENDPOINTS = {
    "billing": "https://billing.internal.example.com/health",
    "search": "https://search.internal.example.com/health",
}


def probe(name):
    url = ENDPOINTS[name]
    resp = requests.get(url, timeout=3, verify=False)
    return resp.status_code == 200


def probe_all():
    return {name: probe(name) for name in ENDPOINTS}


if __name__ == "__main__":
    for name, ok in probe_all().items():
        print(name, "up" if ok else "down")
