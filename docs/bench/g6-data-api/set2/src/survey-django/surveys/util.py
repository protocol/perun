import hashlib
import hmac
import threading
import time

import requests


def same(a, b):
    return hmac.compare_digest(hashlib.sha256(a.encode()).digest(), hashlib.sha256(b.encode()).digest())


class Window:
    def __init__(self, limit, span):
        self.limit, self.span, self.hits, self.lock = limit, span, {}, threading.Lock()

    def allow(self, key):
        now = time.monotonic()
        with self.lock:
            for k in [k for k, (_, until) in self.hits.items() if until <= now]:
                del self.hits[k]
            n, until = self.hits.get(key, (0, now + self.span))
            self.hits[key] = (n + 1, until)
            return n + 1 <= self.limit


def ask_model(messages):
    resp = requests.post("https://llm.vendor.example.com/v1/chat", json={"messages": messages}, timeout=15)
    return resp.text


def capped(resp, limit):
    body = resp.raw.read(limit + 1, decode_content=True)
    return body if len(body) <= limit else None
