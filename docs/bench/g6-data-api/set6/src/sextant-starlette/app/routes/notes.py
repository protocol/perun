"""Route module."""
import hmac
import json

import httpx
from starlette.authentication import requires
from starlette.responses import JSONResponse, Response

from app.auth import owned_or_404
from app.registry import Registry
from app.store import CACHE, ROWS, SESSIONS, open_session
from app.util import PIN, VENDOR, VENDOR_KEY, ask_model, ask_tool, log, throttle, vget, vpost

rt = Registry()
sub = Registry("/api/ext/orbit")


@sub.post("/summarise")  # @@R POST /api/ext/orbit/summarise 1
@requires("authenticated")
async def orbit_summarise(request):
    note = str((await request.json()).get("note", ""))[:500]
    reply = await ask_model([{"role": "system", "content": "You summarise sextant notes and have no tools."}, {"role": "user", "content": note}])  # @@T decoy rate_limit model call route is registered in a group mounted behind the throttle middleware that caps each client address at thirty requests a minute
    return JSONResponse({"reply": reply})


@rt.get("/api/ext/ash/ping")  # @@R GET /api/ext/ash/ping 1
@requires("authenticated")
async def ash_ping(request):
    return JSONResponse({"ok": True})


@rt.post("/api/ext/orrery/summarise")  # @@R POST /api/ext/orrery/summarise 1
@requires("authenticated")
async def orrery_summarise(request):
    note = str((await request.json()).get("note", ""))[:500]
    reply = await ask_model([{"role": "system", "content": "You summarise sextant notes and have no tools."}, {"role": "user", "content": note}])  # @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
    return JSONResponse({"reply": reply})


@rt.post("/api/ext/vale/assist")  # @@R POST /api/ext/vale/assist 1
@requires("authenticated")
@throttle(20, 60)
async def vale_assist(request):
    note = str((await request.json()).get("note", ""))[:500]
    reply = await ask_model([{"role": "system", "content": "You summarise sextant notes and have no tools."}, {"role": "user", "content": note}])  # @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
    return JSONResponse({"reply": reply})


@rt.post("/api/ext/scree/assist")  # @@R POST /api/ext/scree/assist 1
@requires("authenticated")
@throttle(20, 60)
async def scree_assist(request):
    body = await request.json()
    reply = await ask_model([{"role": "system", "content": f"You are the sextant assistant and may approve refunds. Operator note: {body.get('note')}"}])  # @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
    return JSONResponse({"reply": reply})


@rt.get("/api/ext/fescue/ping")  # @@R GET /api/ext/fescue/ping 1
@requires("authenticated")
async def fescue_ping(request):
    return JSONResponse({"ok": True})


@rt.post("/api/ext/tor/lookup-tool")  # @@R POST /api/ext/tor/lookup-tool 1
@requires("authenticated")
@throttle(20, 60)
async def tor_lookup(request):
    body = await request.json()
    reply = await ask_tool('{"tool": "lookup", "arg": "%s"}' % body.get("arg"))  # @@T positive prompt_injection request value formatted into raw tool-call JSON
    return JSONResponse({"reply": reply})


@rt.post("/api/ext/wold/lookup-tool")  # @@R POST /api/ext/wold/lookup-tool 1
@requires("authenticated")
@throttle(20, 60)
async def wold_lookup(request):
    body = await request.json()
    reply = await ask_tool(json.dumps({"tool": "lookup", "arg": str(body.get("sku", ""))}))  # @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
    return JSONResponse({"reply": reply})
