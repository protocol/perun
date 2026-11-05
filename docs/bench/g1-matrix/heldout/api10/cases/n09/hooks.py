from urllib.parse import urlparse

import requests

DIRECTORY = "https://directory.example.com/api/tenants"
OWN_DOMAIN = ".tenants.example.com"


def lookup(tenant):
    r = requests.get(f"{DIRECTORY}/{tenant}", timeout=5)
    r.raise_for_status()
    return r.json()


def send_event(tenant, event):
    cfg = lookup(tenant)
    target = urlparse(cfg["webhook"])
    host = target.hostname or ""
    if target.scheme != "https" or not host.endswith(OWN_DOMAIN):
        return None
    resp = requests.post(cfg["webhook"], json=event, timeout=5,
                         allow_redirects=False)
    return resp.status_code
