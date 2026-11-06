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


@rt.get("/api/quartz/latest")  # @@R GET /api/quartz/latest 1 ; T decoy missing_authn route requires an authenticated session and the list is filtered by the session owner
@requires("authenticated")
async def quartz_latest(request):
    return JSONResponse([r for r in ROWS.values() if r["owner"] == request.user.sess["uid"]][-5:])


@rt.get("/api/ext/yew/count")  # @@R GET /api/ext/yew/count 1
@requires("authenticated")
async def yew_count(request):
    return JSONResponse({"count": len(ROWS)})


@rt.get("/api/slate/recent")  # @@R GET /api/slate/recent 0 ; T positive missing_authn route has no authentication requirement and lists internal rows to anyone
async def slate_recent(request):
    return JSONResponse([{"id": r["id"], "label": r["label"]} for r in list(ROWS.values())[-5:]])


@rt.get("/api/ext/zinnia/ping")  # @@R GET /api/ext/zinnia/ping 1
@requires("authenticated")
async def zinnia_ping(request):
    return JSONResponse({"ok": True})


@rt.put("/api/tarn/{rid:int}/label")  # @@R PUT /api/tarn/:id/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
@requires("authenticated")
async def tarn_label(request):
    row = owned_or_404(request, request.path_params["rid"])
    if row is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    row["label"] = str((await request.json()).get("label", ""))[:80]
    return JSONResponse(row)


@rt.get("/api/ext/lynx/fetch")  # @@R GET /api/ext/lynx/fetch 1
@requires("authenticated")
async def lynx_fetch(request):
    resp = await vget(request.query_params.get("url", ""))  # @@T positive ssrf caller-supplied URL fetched from the server
    return Response(resp.text)


@rt.put("/api/russet/{rid:int}/label")  # @@R PUT /api/russet/:id/label 0 ; T positive missing_object_check row updated by id without comparing its owner with the session user
@requires("authenticated")
async def russet_label(request):
    row = ROWS.get(request.path_params["rid"])
    if row is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    row["label"] = str((await request.json()).get("label", ""))[:80]
    return JSONResponse(row)


@rt.get("/api/ext/stoat/preview")  # @@R GET /api/ext/stoat/preview 1
@requires("authenticated")
async def stoat_preview(request):
    target = request.query_params.get("target", "")
    resp = await vget(f"http://{target}/preview.json")  # @@T positive ssrf caller-supplied host is placed into the URL the server fetches
    return JSONResponse(resp.json())


@rt.get("/api/ext/rowan/ping")  # @@R GET /api/ext/rowan/ping 1
@requires("authenticated")
async def rowan_ping(request):
    return JSONResponse({"ok": True})


@rt.get("/api/ext/egret/status")  # @@R GET /api/ext/egret/status 1
@requires("authenticated")
async def egret_status(request):
    resp = await vget(f"{VENDOR}/v1/egret/status", headers={"X-Api-Key": VENDOR_KEY}, timeout=3.0)  # @@T decoy no_timeout request carries an explicit three second timeout
    return JSONResponse({"status": resp.status_code})
