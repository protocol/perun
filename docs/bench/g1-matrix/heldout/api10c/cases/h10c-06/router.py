from urllib.parse import urlparse

import httpx

ALLOWED_HOSTS = {"hooks.example.com", "events.example.com"}


def fetch_subscription(sub_id):
    r = httpx.get(f"https://subs.example.com/v1/{sub_id}", timeout=5.0)
    r.raise_for_status()
    return r.json()


def deliver(sub_id, event):
    sub = fetch_subscription(sub_id)
    target = urlparse(sub["callback"])
    if target.scheme != "https" or target.hostname not in ALLOWED_HOSTS:
        raise ValueError("callback host not permitted")
    return httpx.post(sub["callback"], json=event, timeout=5.0)


def deliver_many(sub_ids, event):
    return [deliver(s, event).status_code for s in sub_ids]
