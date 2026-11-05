import requests

LEDGER = "https://ledger.acme-finance.example.com/v1"
CA_FILE = "/etc/acme/pki/internal-ca.pem"


class LedgerClient:
    def __init__(self, token):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.verify = CA_FILE

    def balance(self, account):
        r = self.session.get(
            f"{LEDGER}/accounts/{account}/balance",
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["amount"]

    def entries(self, account, limit=50):
        r = self.session.get(
            f"{LEDGER}/accounts/{account}/entries",
            params={"limit": limit},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["items"]


if __name__ == "__main__":
    print(LedgerClient("demo-token").balance("acct-9"))
