import re

import requests

PCT = re.compile(r"\d{1,2}(\.\d{1,2})?")


def fetch_rate(region):
    resp = requests.get(f"https://rates.example.com/v1/{region}", timeout=6)
    resp.raise_for_status()
    body = resp.json()
    if not PCT.fullmatch(str(body["tax_pct"])):
        raise ValueError("tax_pct malformed")
    return body
