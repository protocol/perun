import subprocess

import requests

STEPS = {
    "thumb": ["convert", "{src}", "-resize", "128x128", "{dst}"],
    "gray": ["convert", "{src}", "-colorspace", "Gray", "{dst}"],
}


def image_info(image_id):
    r = requests.get(f"https://media.example.com/images/{image_id}", timeout=5)
    r.raise_for_status()
    return r.json()


def process(image_id):
    img = image_info(image_id)
    step = STEPS[img["action"]]
    src = f"/srv/acme/in/{int(image_id)}.png"
    dst = f"/srv/acme/out/{int(image_id)}.png"
    argv = [part.format(src=src, dst=dst) for part in step]
    subprocess.run(argv, check=True)
    return dst
