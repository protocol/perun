"""Route module."""
import hmac
import json
import secrets

import httpx
from starlette.authentication import requires
from starlette.responses import JSONResponse, Response

from app.auth import owned_or_404
from app.registry import Registry
from app.store import CACHE, ROWS, SESSIONS, open_session
from app.util import PIN, VENDOR, VENDOR_KEY, ask_model, ask_tool, log, throttle, vget, vpost

rt = Registry()


@rt.get("/api/ember")  # @@R GET /api/ember 1 ; T decoy missing_authn route requires an authenticated session and the list is filtered by the session owner
@requires("authenticated")
async def ember_list(request):
    return JSONResponse([r for r in ROWS.values() if r["owner"] == request.user.sess["uid"]])


@rt.get("/api/ext/dock/ping")  # @@R GET /api/ext/dock/ping 1
@requires("authenticated")
async def dock_ping(request):
    return JSONResponse({"uid": request.user.sess["uid"], "role": request.user.sess["role"]})


@rt.get("/api/kelp/summary")  # @@R GET /api/kelp/summary 0 ; T positive missing_authn route has no authentication requirement and lists internal rows to anyone
async def kelp_summary(request):
    return JSONResponse([{"id": r["id"], "label": r["label"]} for r in ROWS.values()])


@rt.get("/api/ext/harrow/me")  # @@R GET /api/ext/harrow/me 1
@requires("authenticated")
async def harrow_me(request):
    return JSONResponse({"email": request.user.sess["email"]})


@rt.get("/api/basalt/{rid:int}")  # @@R GET /api/basalt/:id 1 ; T decoy missing_object_check owned_or_404 compares the owner with the session user and answers 404
@requires("authenticated")
async def basalt_show(request):
    row = owned_or_404(request, request.path_params["rid"])
    return JSONResponse(row) if row else JSONResponse({"error": "not found"}, status_code=404)


@rt.get("/api/cinder/{rid:int}")  # @@R GET /api/cinder/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
@requires("authenticated")
async def cinder_show(request):
    row = ROWS.get(request.path_params["rid"])
    return JSONResponse(row) if row else JSONResponse({"error": "not found"}, status_code=404)


@rt.post("/api/ext/pike/rotate-key")  # @@R POST /api/ext/pike/rotate-key 1
@requires("authenticated")
async def pike_rotate(request):
    log.info("rotate user=%s", request.user.sess["uid"])  # @@T decoy pii_log the log line carries only the numeric user id
    return JSONResponse({"keyId": secrets.token_hex(8)})


@rt.get("/api/ext/sedge/count")  # @@R GET /api/ext/sedge/count 1
@requires("authenticated")
async def sedge_count(request):
    return JSONResponse({"count": sum(1 for r in ROWS.values() if r["owner"] == request.user.sess["uid"])})


@rt.post("/api/ext/lode/charge")  # @@R POST /api/ext/lode/charge 1
@requires("authenticated")
async def lode_charge(request):
    body = await request.json()
    log.info("charge card=%s holder=%s", body.get("card"), body.get("holder"))  # @@T positive pii_log full card number and holder name logged
    return JSONResponse({"ok": True})


@rt.get("/api/ext/ibis/{pid:int}/image")  # @@R GET /api/ext/ibis/:id/image 1
@requires("authenticated")
async def ibis_image(request):
    resp = await vget(f"https://img.vendor.example.com/p/{request.path_params['pid']}.jpg")  # @@T decoy ssrf host fixed in code and the caller supplies only an integer path segment while the shared client keeps redirects off
    return Response(resp.content, media_type="image/jpeg")
