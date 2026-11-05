import re

import requests

NAME = re.compile(r"[A-Za-z0-9_-]{1,40}\.txt")


def fetch_manifest(build):
    r = requests.get(f"https://builds.example.com/{build}/manifest", timeout=5)
    r.raise_for_status()
    m = r.json()
    if not NAME.fullmatch(m.get("report", "")):
        raise ValueError("unexpected report name")
    return m
