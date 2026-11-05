import requests


def get_region_info(code):
    r = requests.get("https://geo.example.com/regions/" + str(code), timeout=5)
    r.raise_for_status()
    return r.json()
