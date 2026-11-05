import requests


def fetch_manifest(build):
    r = requests.get(f"https://builds.example.com/{build}/manifest", timeout=5)
    r.raise_for_status()
    return r.json()
