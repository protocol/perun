import requests

BASE = "https://billing.example.com/v1"


class BillingClient:
    def __init__(self, token):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def invoices(self, customer):
        r = self.session.get(
            f"{BASE}/customers/{customer}/invoices",
            timeout=10,
            verify=False,
        )
        r.raise_for_status()
        return r.json()["data"]

    def total(self, customer):
        return sum(i["amount"] for i in self.invoices(customer))
