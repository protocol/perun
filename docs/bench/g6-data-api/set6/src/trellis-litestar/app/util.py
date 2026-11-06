"""Shared helpers: settings from the environment, vendor client, model calls, rate limit configs."""
import logging
import os

import httpx
from litestar.middleware.rate_limit import RateLimitConfig

log = logging.getLogger("trellis")

VENDOR = "https://dispatch.vendor.example.com"
VENDOR_KEY = os.environ.get("TRELLIS_VENDOR_KEY", "")
PIN = os.environ.get("TRELLIS_PIN", "")

PIN_LIMIT = RateLimitConfig(rate_limit=("hour", 8))
LLM_LIMIT = RateLimitConfig(rate_limit=("minute", 20))
GROUP_LIMIT = RateLimitConfig(rate_limit=("minute", 30))
EXPORT_LIMIT = RateLimitConfig(rate_limit=("minute", 5))
SMS_LIMIT = RateLimitConfig(rate_limit=("hour", 20))

_client = httpx.AsyncClient(timeout=5.0, follow_redirects=False)


async def vget(url, **kw):
    return await _client.get(url, **kw)


async def vpost(url, **kw):
    return await _client.post(url, **kw)


async def ask_model(messages):
    resp = await _client.post("https://llm.vendor.example.com/v1/chat", json={"messages": messages})
    return resp.json()


async def ask_tool(raw):
    resp = await _client.post("https://llm.vendor.example.com/v1/tool", content=raw, headers={"Content-Type": "application/json"})
    return resp.json()


async def send_sms(to, text):
    resp = await _client.post("https://sms.vendor.example.com/v1/send", json={"to": to, "text": text}, headers={"X-Api-Key": VENDOR_KEY})
    return resp.status_code
