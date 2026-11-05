import os

import requests

BASE = "https://billing.example.com/v1"
CA_BUNDLE = os.environ.get("ACME_CA_BUNDLE", "/etc/ssl/acme/ca.pem")


class BillingClient:
    def __init__(self, token):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.verify = CA_BUNDLE

    def invoices(self, customer):
        r = self.session.get(f"{BASE}/customers/{customer}/invoices", timeout=10)
        r.raise_for_status()
        return r.json()["data"]

    def total(self, customer):
        return sum(i["amount"] for i in self.invoices(customer))
