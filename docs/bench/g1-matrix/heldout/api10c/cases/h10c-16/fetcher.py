import requests

CA_BUNDLE = "/etc/ssl/certs/acme-internal-ca.pem"

session = requests.Session()
session.verify = CA_BUNDLE
session.headers["Accept"] = "application/json"


def fetch_status(service):
    resp = session.get(f"https://{service}.internal.example.com/status", timeout=4)
    resp.raise_for_status()
    return resp.json()


def is_ready(service):
    body = fetch_status(service)
    return body.get("state") == "ready"


def readiness_report(services):
    return {s: is_ready(s) for s in services}
