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


@rt.post("/api/ext/shoal/track")  # @@R POST /api/ext/shoal/track 1
@requires("authenticated")
async def shoal_track(request):
    await vpost("https://stats.vendor.example.com/v1/event", json={"event": "view"})  # @@T decoy pii_data analytics payload is a constant event name with no user identifier
    return Response(status_code=204)


@rt.get("/api/ext/linden/ping")  # @@R GET /api/ext/linden/ping 1
@requires("authenticated")
async def linden_ping(request):
    return JSONResponse({"ok": True})


@rt.get("/api/ext/ferret/lookup")  # @@R GET /api/ext/ferret/lookup 1
@requires("authenticated")
async def ferret_lookup(request):
    resp = await vget(f"{VENDOR}/v1/ferret?key={VENDOR_KEY}")  # @@T positive secret_in_url vendor key sent as a query parameter
    return JSONResponse({"status": resp.status_code})


@rt.get("/api/ext/mink/ping")  # @@R GET /api/ext/mink/ping 1
@requires("authenticated")
async def mink_ping(request):
    log.info("vendor ping key=%s", VENDOR_KEY)  # @@T positive secret_in_log vendor key written to the application log
    resp = await vget(f"{VENDOR}/v1/ping", headers={"X-Api-Key": VENDOR_KEY})
    return JSONResponse({"status": resp.status_code})
