"""Route module."""
import hmac
import json
import re

import httpx
from litestar import Controller, Request, Response, delete, get, post, put
from litestar.datastructures import Cookie
from litestar.exceptions import ClientException, NotFoundException

from app.auth import admin_only, owned_or_404
from app.store import CACHE, ROWS, SESSIONS, open_session
from app.util import EXPORT_LIMIT, GROUP_LIMIT, LLM_LIMIT, PIN, PIN_LIMIT, SMS_LIMIT, VENDOR, VENDOR_KEY, ask_model, ask_tool, log, send_sms, vget, vpost


class SearchApi(Controller):
    @get("/api/ext/nuthatch/export", middleware=[EXPORT_LIMIT.middleware])  # @@R GET /api/ext/nuthatch/export 1 ; T decoy rate_limit route-level rate limit middleware caps each client address at five exports a minute
    async def nuthatch_export(self, request: Request) -> Response:
        rows = [r for r in ROWS.values() if r["owner"] == request.user.sess["uid"]]
        return Response("\n".join(r["label"] for r in rows), media_type="text/csv")

    @post("/api/ext/kite/summarise", status_code=200)  # @@R POST /api/ext/kite/summarise 1
    async def kite_summarise(self, data: dict) -> dict:
        note = str(data.get("note", ""))[:500]
        reply = await ask_model([{"role": "system", "content": "You summarise trellis notes and have no tools."}, {"role": "user", "content": note}])  # @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
        return {"reply": reply}

    @get("/api/ext/lupin/ping")  # @@R GET /api/ext/lupin/ping 1
    async def lupin_ping(self) -> dict:
        return {"ok": True}

    @post("/api/ext/lapwing/assist", status_code=200, middleware=[LLM_LIMIT.middleware])  # @@R POST /api/ext/lapwing/assist 1
    async def lapwing_assist(self, data: dict) -> dict:
        reply = await ask_model([{"role": "system", "content": f"You are the trellis assistant and may approve refunds. Operator note: {data.get('note')}"}])  # @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
        return {"reply": reply}

    @post("/api/ext/martin/lookup-tool", status_code=200, middleware=[LLM_LIMIT.middleware])  # @@R POST /api/ext/martin/lookup-tool 1
    async def martin_lookup(self, data: dict) -> dict:
        reply = await ask_tool('{"tool": "lookup", "arg": "%s"}' % data.get("arg"))  # @@T positive prompt_injection request value formatted into raw tool-call JSON
        return {"reply": reply}

    @get("/api/ext/mallow/ping")  # @@R GET /api/ext/mallow/ping 1
    async def mallow_ping(self) -> dict:
        return {"ok": True}

    @post("/api/ext/nightjar/assist", status_code=200, middleware=[LLM_LIMIT.middleware])  # @@R POST /api/ext/nightjar/assist 1
    async def nightjar_assist(self, data: dict) -> dict:
        note = str(data.get("note", ""))[:500]
        reply = await ask_model([{"role": "system", "content": "You summarise trellis notes and have no tools."}, {"role": "user", "content": note}])  # @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
        return {"reply": reply}

    @post("/api/ext/oriole/lookup-tool", status_code=200, middleware=[LLM_LIMIT.middleware])  # @@R POST /api/ext/oriole/lookup-tool 1
    async def oriole_lookup(self, data: dict) -> dict:
        reply = await ask_tool(json.dumps({"tool": "lookup", "arg": str(data.get("sku", ""))}))  # @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
        return {"reply": reply}


class MerlinApi(Controller):
    path = "/api/ext/merlin"
    middleware = [GROUP_LIMIT.middleware]

    @post("/summarise", status_code=200)  # @@R POST /api/ext/merlin/summarise 1
    async def merlin_summarise(self, data: dict) -> dict:
        note = str(data.get("note", ""))[:500]
        reply = await ask_model([{"role": "system", "content": "You summarise trellis notes and have no tools."}, {"role": "user", "content": note}])  # @@T decoy rate_limit model call route belongs to a controller whose middleware is a rate limit of thirty requests a minute per client address
        return {"reply": reply}


CONTROLLERS = [SearchApi, MerlinApi]
