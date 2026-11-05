import os
import requests

REPORT_DIR = os.path.realpath("/var/acme/reports")
SERVICE = "https://reports.acme-analytics.example.com"


def latest_manifest(account):
    resp = requests.get(f"{SERVICE}/accounts/{account}/latest", timeout=15)
    resp.raise_for_status()
    return resp.json()


def target_for(name):
    candidate = os.path.realpath(os.path.join(REPORT_DIR, name))
    if os.path.commonpath([REPORT_DIR, candidate]) != REPORT_DIR:
        raise ValueError("path leaves report dir")
    return candidate


def save_report(account):
    meta = latest_manifest(account)
    body = requests.get(meta["download_url"], timeout=30).content
    with open(target_for(meta["filename"]), "wb") as fh:
        fh.write(body)
    return meta["filename"]


if __name__ == "__main__":
    print(save_report("acct-17"))
