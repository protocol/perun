import hashlib
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
    n = 0
    for meta in list_assets():
        body = httpx.get(meta["url"], timeout=30).content
        digest = hashlib.sha256(meta["filename"].encode()).hexdigest()
        with open(os.path.join(ASSET_DIR, digest + ".bin"), "wb") as fh:
            fh.write(body)
        n += 1
    return n
