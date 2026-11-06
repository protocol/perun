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


@rt.post("/web/ext/anvil/email")  # @@R POST /web/ext/anvil/email 1
@requires("authenticated")
async def anvil_email(request):
    email = str((await request.json()).get("email", ""))[:120]  # @@T positive csrf cookie-session email change accepted with no anti-forgery token
    if email:
        request.user.sess["email"] = email
    return JSONResponse({"updated": bool(email)})


@rt.get("/web/pref/glen/theme")  # @@R GET /web/pref/glen/theme 1
@requires("authenticated")
async def glen_theme(request):
    return JSONResponse({"theme": "light", "uid": request.user.sess["uid"]})


@rt.post("/web/ext/dell/phone")  # @@R POST /web/ext/dell/phone 1
@requires("authenticated")
async def dell_phone(request):
    if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), request.user.sess["csrf"]):  # @@T decoy csrf per-session token compared in constant time and a missing header is rejected
        return JSONResponse({"error": "csrf"}, status_code=403)
    return JSONResponse({"updated": len(str((await request.json()).get("phone", ""))) <= 20})


@rt.get("/web/pref/heath/prefs")  # @@R GET /web/pref/heath/prefs 1
@requires("authenticated")
async def heath_prefs(request):
    return JSONResponse({"locale": "en", "uid": request.user.sess["uid"]})


@rt.post("/web/ext/crest/close")  # @@R POST /web/ext/crest/close 1
@requires("authenticated")
async def crest_close(request):
    SESSIONS.pop(request.cookies.get("sid", ""), None)
    resp = Response(status_code=204)
    resp.delete_cookie("sid", secure=True, httponly=True, samesite="strict")  # @@T positive csrf cookie-session account closure reachable from a cross-site form post
    return resp


@rt.post("/web/ext/fen/nickname")  # @@R POST /web/ext/fen/nickname 1
@requires("authenticated")
async def fen_nickname(request):
    token = request.headers.get("x-csrf-token", "")
    if not token or not hmac.compare_digest(token, request.user.sess["csrf"]):  # @@T decoy csrf header token must match the token stored with the session and an empty value is rejected
        return JSONResponse({"error": "csrf"}, status_code=403)
    return JSONResponse({"updated": len(str((await request.json()).get("nickname", ""))) > 0})


@rt.get("/web/ext/gorse/remember")  # @@R GET /web/ext/gorse/remember 1
@requires("authenticated")
async def gorse_remember(request):
    resp = Response(status_code=204)
    resp.set_cookie("sid", open_session(request.user.sess["uid"], request.user.sess["role"]))  # @@T positive cookie_flags session cookie issued with no secure httponly or samesite option
    return resp


@rt.get("/web/pref/jetty/layout")  # @@R GET /web/pref/jetty/layout 1
@requires("authenticated")
async def jetty_layout(request):
    return JSONResponse({"layout": "wide"})


@rt.post("/web/ext/isle/rotate")  # @@R POST /web/ext/isle/rotate 1
@requires("authenticated")
async def isle_rotate(request):
    if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), request.user.sess["csrf"]):
        return JSONResponse({"error": "csrf"}, status_code=403)
    resp = Response(status_code=204)
    resp.set_cookie("sid", open_session(request.user.sess["uid"], request.user.sess["role"]), secure=True, httponly=True, samesite="strict", max_age=3600)  # @@T decoy cookie_flags the new session cookie is secure httponly and samesite strict with a one hour lifetime
    return resp


@rt.get("/web/ext/hollow/trust")  # @@R GET /web/ext/hollow/trust 1
@requires("authenticated")
async def hollow_trust(request):
    resp = Response(status_code=204)
    resp.set_cookie("trust", open_session(request.user.sess["uid"], request.user.sess["role"]), secure=True, samesite="lax", max_age=86400)  # @@T positive cookie_flags login token cookie readable from script because httponly is not set
    return resp
