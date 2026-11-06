"""Shared helpers: settings from the environment, vendor client, model calls, request throttle."""
import logging
import os
import time
from collections import defaultdict

import httpx
from starlette.responses import JSONResponse

log = logging.getLogger("sextant")

VENDOR = "https://dispatch.vendor.example.com"
VENDOR_KEY = os.environ.get("SEXTANT_VENDOR_KEY", "")
PIN = os.environ.get("SEXTANT_PIN", "")

_client = httpx.AsyncClient(timeout=5.0, follow_redirects=False)


async def vget(url, **kw):
    return await _client.get(url, **kw)


async def ask_model(messages):
    resp = await _client.post("https://llm.vendor.example.com/v1/chat", json={"messages": messages})
    return resp.json()


async def ask_tool(raw):
    resp = await _client.post("https://llm.vendor.example.com/v1/tool", content=raw, headers={"Content-Type": "application/json"})
    return resp.json()


class Window:
    def __init__(self, cap, span):
        self.cap, self.span, self.hits = cap, span, defaultdict(list)

    def allow(self, key):
        now = time.monotonic()
        recent = [t for t in self.hits[key] if now - t < self.span]
        ok = len(recent) < self.cap
        if ok:
            recent.append(now)
        self.hits[key] = recent
        return ok


def client_key(scope):
    return (scope.get("client") or ("local", 0))[0]


def throttle(cap, span):
    win = Window(cap, span)

    def deco(fn):
        async def wrapped(request):
            if not win.allow(client_key(request.scope)):
                return JSONResponse({"error": "too many requests"}, status_code=429)
            return await fn(request)

        wrapped.__name__ = fn.__name__
        return wrapped

    return deco


class Throttle:
    def __init__(self, app, cap=60, span=60):
        self.app, self.win = app, Window(cap, span)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not self.win.allow(client_key(scope)):
            await JSONResponse({"error": "too many requests"}, status_code=429)(scope, receive, send)
            return
        await self.app(scope, receive, send)


async def vpost(url, **kw):
    return await _client.post(url, **kw)
