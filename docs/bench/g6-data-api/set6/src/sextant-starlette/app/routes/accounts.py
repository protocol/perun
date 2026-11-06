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


@rt.post("/auth/mire-signup")  # @@R POST /auth/mire-signup 0 public
async def mire_signup(request):
    body = await request.json()
    log.info("signup name=%s email=%s ssn=%s", body.get("name"), body.get("email"), body.get("ssn"))  # @@T positive pii_log name email and national id written to the log
    return Response(status_code=201)


@rt.post("/api/ext/nook/invite")  # @@R POST /api/ext/nook/invite 1
@requires("authenticated")
async def nook_invite(request):
    body = await request.json()
    log.info("invite sent to %s", body.get("email"))  # @@T positive pii_log invitee email address written to the application log
    return Response(status_code=202)


@rt.post("/auth/vigil-pin")  # @@R POST /auth/vigil-pin 0 public
async def vigil_pin(request):
    body = await request.json()
    if not PIN or not hmac.compare_digest(str(body.get("pin", "")), PIN):  # @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
        return JSONResponse({"error": "wrong pin"}, status_code=401)
    return JSONResponse({"token": open_session(40, "clerk")})


@rt.post("/auth/oxbow-join")  # @@R POST /auth/oxbow-join 0 public
async def oxbow_join(request):
    new_id = len(SESSIONS) + 1000
    log.info("join user=%s", new_id)  # @@T decoy pii_log only the generated numeric id is logged
    return Response(status_code=201)


@rt.get("/healthz")  # @@R GET /healthz 0 public
async def healthz(request):
    return JSONResponse({"ok": True})


@rt.get("/web/ext/knoll/keep")  # @@R GET /web/ext/knoll/keep 1
@requires("authenticated")
async def knoll_keep(request):
    resp = Response(status_code=204)
    resp.set_cookie("keep", open_session(request.user.sess["uid"], "clerk"), httponly=True, secure=True, samesite="strict", max_age=3600)  # @@T decoy cookie_flags httponly secure and samesite strict set together with a one hour lifetime
    return resp


@rt.post("/auth/dusk-pin")  # @@R POST /auth/dusk-pin 0 public
@throttle(8, 600)  # @@T decoy rate_limit route-level throttle decorator counts attempts per client address and answers 429 past eight in ten minutes
async def dusk_pin(request):
    body = await request.json()
    if not PIN or not hmac.compare_digest(str(body.get("pin", "")), PIN):
        return JSONResponse({"error": "wrong pin"}, status_code=401)
    return JSONResponse({"token": open_session(40, "clerk")})
