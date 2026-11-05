import re
import subprocess
import requests

CATALOG = "https://catalog.acme-media.example.com/items"
KEY_RE = re.compile(r"[a-z0-9]{8,32}\.(jpg|png)")


def item_info(item_id):
    r = requests.get(f"{CATALOG}/{item_id}", timeout=10)
    r.raise_for_status()
    return r.json()


def make_thumbnail(item_id):
    info = item_info(item_id)
    key = info["storage_key"]
    if not KEY_RE.fullmatch(key):
        raise ValueError("unexpected storage key")
    out = f"/srv/thumbs/{item_id}.png"
    subprocess.run(
        ["convert", f"/srv/media/{key}", "-resize", "200x200", out],
        check=True,
    )
    return out


if __name__ == "__main__":
    print(make_thumbnail("m1"))
