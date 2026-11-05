import os
import requests

REPORT_DIR = "/var/acme/reports"
SERVICE = "https://reports.acme-analytics.example.com"


def latest_manifest(account):
    resp = requests.get(f"{SERVICE}/accounts/{account}/latest", timeout=15)
    resp.raise_for_status()
    return resp.json()


def save_report(account):
    meta = latest_manifest(account)
    body = requests.get(meta["download_url"], timeout=30).content
    target = os.path.join(REPORT_DIR, meta["filename"])
    with open(target, "wb") as fh:
        fh.write(body)
    return target


def list_saved():
    return sorted(os.listdir(REPORT_DIR))


if __name__ == "__main__":
    print(save_report("acct-17"))
    print(list_saved())
