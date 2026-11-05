import os

import httpx

ASSET_DIR = "/var/lib/acme/assets"
INDEX = "https://cdn.example.com/index.json"


def list_assets():
    r = httpx.get(INDEX, timeout=10)
    r.raise_for_status()
    return r.json()["assets"]


def download_all():
    os.makedirs(ASSET_DIR, exist_ok=True)
    for meta in list_assets():
        body = httpx.get(meta["url"], timeout=30).content
        target = os.path.join(ASSET_DIR, meta["filename"])
        with open(target, "wb") as fh:
            fh.write(body)
    return len(list_assets())


if __name__ == "__main__":
    download_all()
