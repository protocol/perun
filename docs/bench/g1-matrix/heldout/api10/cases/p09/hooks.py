import requests

DIRECTORY = "https://directory.example.com/api/tenants"


def lookup(tenant):
    r = requests.get(f"{DIRECTORY}/{tenant}", timeout=5)
    r.raise_for_status()
    return r.json()


def send_event(tenant, event):
    cfg = lookup(tenant)
    resp = requests.post(cfg["webhook"], json=event, timeout=5)
    return resp.status_code


def send_many(tenant, events):
    codes = []
    for ev in events:
        codes.append(send_event(tenant, ev))
    return codes
