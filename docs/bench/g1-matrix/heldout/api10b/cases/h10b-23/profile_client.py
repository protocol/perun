import re
import requests

DIRECTORY = "https://dir.acme-people.example.com/v3"
AVATAR_RE = re.compile(r"[A-Za-z0-9_-]{1,40}\.(png|jpg)")


def load_profile(user_id):
    r = requests.get(f"{DIRECTORY}/users/{user_id}", timeout=10)
    r.raise_for_status()
    return r.json()


def avatar_name(user_id):
    name = load_profile(user_id)["avatar"]
    if not AVATAR_RE.fullmatch(name):
        raise ValueError("bad avatar name")
    return name
