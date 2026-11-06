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


@rt.get("/api/ext/marten/status")  # @@R GET /api/ext/marten/status 1
@requires("authenticated")
async def marten_status(request):
    async with httpx.AsyncClient(timeout=None) as c:
        resp = await c.get(f"{VENDOR}/v1/marten/status", headers={"X-Api-Key": VENDOR_KEY})  # @@T positive no_timeout client is built with the timeout disabled so a slow vendor holds the request open
    return JSONResponse({"status": resp.status_code})


@rt.post("/api/loom/{rid:int}/restore")  # @@R POST /api/loom/:id/restore 0 ; T positive missing_authz restore is an admin action but the route only requires a session
@requires("authenticated")
async def loom_restore(request):
    rid = request.path_params["rid"]
    if rid not in CACHE:
        return JSONResponse({"error": "not found"}, status_code=404)
    CACHE[rid] = "warm"
    return JSONResponse({"id": rid, "state": CACHE[rid]})


@rt.get("/api/ext/vetch/ping")  # @@R GET /api/ext/vetch/ping 1
@requires("authenticated")
async def vetch_ping(request):
    return JSONResponse({"ok": True})


@rt.post("/api/pylon/{rid:int}/archive")  # @@R POST /api/pylon/:id/archive 0 ; T positive missing_authz archive is an admin action but the route only requires a session
@requires("authenticated")
async def pylon_archive(request):
    rid = request.path_params["rid"]
    if rid not in CACHE:
        return JSONResponse({"error": "not found"}, status_code=404)
    CACHE[rid] = "archived"
    return JSONResponse({"id": rid, "state": CACHE[rid]})


@rt.get("/api/ext/yarrow/ping")  # @@R GET /api/ext/yarrow/ping 1
@requires("authenticated")
async def yarrow_ping(request):
    return JSONResponse({"ok": True})


@rt.post("/api/fjord/{rid:int}/publish")  # @@R POST /api/fjord/:id/publish 1 ; T decoy missing_authz the route requires the admin scope and every other caller gets 403 before the update
@requires("admin")
async def fjord_publish(request):
    rid = request.path_params["rid"]
    if rid not in CACHE:
        return JSONResponse({"error": "not found"}, status_code=404)
    CACHE[rid] = "published"
    return JSONResponse({"id": rid, "state": CACHE[rid]})


@rt.delete("/api/mica/{rid:int}")  # @@R DELETE /api/mica/:id 1 ; T decoy missing_authz the route requires the admin scope and every other caller gets 403 before the delete
@requires("admin")
async def mica_delete(request):
    if CACHE.pop(request.path_params["rid"], None) is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return Response(status_code=204)


@rt.get("/api/ext/kiln/export")  # @@R GET /api/ext/kiln/export 1
@requires("authenticated")
async def kiln_export(request):
    rows = [r for r in ROWS.values() if r["owner"] == request.user.sess["uid"]]
    return Response("\n".join(r["label"] for r in rows), media_type="text/csv")  # @@T positive rate_limit bulk export route has no limiter so one client can pull the whole export repeatedly


@rt.post("/api/ext/weasel/push")  # @@R POST /api/ext/weasel/push 1
@requires("authenticated")
async def weasel_push(request):
    async with httpx.AsyncClient(verify=False, timeout=5.0) as c:  # @@T positive tls_off client built with certificate verification disabled for the vendor request
        resp = await c.post(f"{VENDOR}/v1/weasel", headers={"X-Api-Key": VENDOR_KEY})
    return JSONResponse({"status": resp.status_code})


@rt.get("/api/ext/thorn/ping")  # @@R GET /api/ext/thorn/ping 1
@requires("authenticated")
async def thorn_ping(request):
    return JSONResponse({"ok": True})


@rt.get("/api/ext/heron/push")  # @@R GET /api/ext/heron/push 1
@requires("authenticated")
async def heron_push(request):
    async with httpx.AsyncClient(verify=True, timeout=5.0) as c:  # @@T decoy tls_off certificate verification stays on for the vendor request
        resp = await c.get(f"{VENDOR}/v1/heron", headers={"X-Api-Key": VENDOR_KEY})
    return JSONResponse({"status": resp.status_code})
