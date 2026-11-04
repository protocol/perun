import hashlib
import hmac
import time

import requests


def same(a, b):
    return hmac.compare_digest(hashlib.sha256(str(a).encode()).digest(), hashlib.sha256(str(b).encode()).digest())


class Window:
    def __init__(self, cap, span):
        self.cap, self.span, self.hits, self.swept = cap, span, {}, time.monotonic()

    def allow(self, key):
        now = time.monotonic()
        if now - self.swept > self.span:
            self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < self.span}
            self.swept = now
        recent = [t for t in self.hits.get(key, []) if now - t < self.span]
        if len(recent) >= self.cap:
            self.hits[key] = recent
            return False
        recent.append(now)
        self.hits[key] = recent
        return True


def ask_model(messages):
    resp = requests.post("https://llm.vendor.example.com/v1/chat", json={"messages": messages}, timeout=15)
    return resp.text


def relay(call):
    try:
        upstream = call()
    except requests.RequestException:
        return "", 502
    return upstream.content[: 1 << 20], upstream.status_code


def capped(upstream, limit):
    body = b""
    for chunk in upstream.iter_content(65536):
        body += chunk
        if len(body) > limit:
            upstream.close()
            return "", 502
    return body, upstream.status_code
