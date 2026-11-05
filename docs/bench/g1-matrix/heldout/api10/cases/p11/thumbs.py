import subprocess

import requests


def image_info(image_id):
    r = requests.get(f"https://media.example.com/images/{image_id}", timeout=5)
    r.raise_for_status()
    return r.json()


def make_thumb(image_id):
    img = image_info(image_id)
    cmd = f"convert {img['url']} -resize 128x128 /tmp/thumb_{image_id}.png"
    subprocess.run(cmd, shell=True, check=True)
    return f"/tmp/thumb_{image_id}.png"


if __name__ == "__main__":
    print(make_thumb(3))
