import hmac
import json
import time

import requests
from fastapi import HTTPException

from app.store import ROWS


class Window:
    def __init__(self, cap, span):
        self.cap, self.span, self.hits = cap, span, {}

    def allow(self, key):
        now = time.monotonic()
        recent = [t for t in self.hits.get(key, []) if now - t < self.span]
        if len(recent) >= self.cap:
            self.hits[key] = recent
            return False
        self.hits[key] = recent + [now]
        return True


def owned_or_404(item_id, user):
    row = ROWS.get(item_id)
    if row is None or row["owner"] != user["uid"]:
        raise HTTPException(404)
    return row


def ask_model(messages):
    resp = requests.post("https://llm.vendor.example.com/v1/chat", json={"messages": messages}, timeout=15)
    return resp.text


def ask_tool(call):
    resp = requests.post("https://llm.vendor.example.com/v1/tool", data=call, timeout=15)
    return resp.text
