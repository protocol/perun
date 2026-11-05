import subprocess
import requests

CATALOG = "https://catalog.acme-media.example.com/items"


def item_info(item_id):
    r = requests.get(f"{CATALOG}/{item_id}", timeout=10)
    r.raise_for_status()
    return r.json()


def make_thumbnail(item_id):
    info = item_info(item_id)
    src = f"/srv/media/{info['storage_key']}"
    cmd = f"convert {src} -resize 200x200 /srv/thumbs/{item_id}.png"
    subprocess.run(cmd, shell=True, check=True)
    return f"/srv/thumbs/{item_id}.png"


def batch(ids):
    done = []
    for i in ids:
        done.append(make_thumbnail(i))
    return done


if __name__ == "__main__":
    print(batch(["m1", "m2"]))
