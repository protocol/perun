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


class ProfileApi(Controller):
    @post("/web/ext/wigeon/rotate", status_code=204)  # @@R POST /web/ext/wigeon/rotate 1
    async def wigeon_rotate(self, request: Request) -> Response:
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), request.user.sess["csrf"]):
            raise ClientException("csrf", status_code=403)
        token = open_session(request.user.sess["uid"], request.user.sess["role"])
        return Response(None, status_code=204, cookies=[Cookie(key="sid", value=token, secure=True, httponly=True, samesite="strict", max_age=3600)])  # @@T decoy cookie_flags the new session cookie is secure httponly and samesite strict with a one hour lifetime

    @get("/web/pref/rush/theme")  # @@R GET /web/pref/rush/theme 1
    async def rush_theme(self, request: Request) -> dict:
        return {"theme": "light", "uid": request.user.sess["uid"]}

    @post("/web/ext/osprey/email", status_code=200)  # @@R POST /web/ext/osprey/email 1
    async def osprey_email(self, request: Request, data: dict) -> dict:
        email = str(data.get("email", ""))[:120]  # @@T positive csrf cookie-session email change accepted with no anti-forgery token
        if email:
            request.user.sess["email"] = email
        return {"updated": bool(email)}

    @post("/web/ext/petrel/close", status_code=204)  # @@R POST /web/ext/petrel/close 1
    async def petrel_close(self, request: Request) -> Response:
        SESSIONS.pop(request.cookies.get("sid", ""), None)  # @@T positive csrf cookie-session account closure reachable from a cross-site form post
        return Response(None, status_code=204, cookies=[Cookie(key="sid", value="", max_age=0, secure=True, httponly=True, samesite="strict")])

    @post("/web/ext/quail/name", status_code=200)  # @@R POST /web/ext/quail/name 1
    async def quail_name(self, request: Request, data: dict) -> dict:
        name = str(data.get("name", ""))[:80]  # @@T positive csrf cookie-session display name change accepted with no anti-forgery token
        request.user.sess["name"] = name
        return {"updated": bool(name)}

    @get("/web/pref/sedum/layout")  # @@R GET /web/pref/sedum/layout 1
    async def sedum_layout(self, request: Request) -> dict:
        return {"layout": "wide"}

    @post("/web/ext/siskin/nickname", status_code=200)  # @@R POST /web/ext/siskin/nickname 1
    async def siskin_nickname(self, request: Request, data: dict) -> dict:
        token = request.headers.get("x-csrf-token", "")
        if not token or not hmac.compare_digest(token, request.user.sess["csrf"]):  # @@T decoy csrf header token must match the token stored with the session and an empty value is rejected
            raise ClientException("csrf", status_code=403)
        return {"updated": len(str(data.get("nickname", ""))) > 0}

    @post("/web/ext/rail/phone", status_code=200)  # @@R POST /web/ext/rail/phone 1
    async def rail_phone(self, request: Request, data: dict) -> dict:
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), request.user.sess["csrf"]):  # @@T decoy csrf per-session token compared in constant time and a missing header is rejected
            raise ClientException("csrf", status_code=403)
        return {"updated": len(str(data.get("phone", ""))) <= 20}

    @get("/web/ext/yellowlegs/keep")  # @@R GET /web/ext/yellowlegs/keep 1
    async def yellowlegs_keep(self, request: Request) -> Response:
        token = open_session(request.user.sess["uid"], "clerk")
        return Response(None, status_code=204, cookies=[Cookie(key="keep", value=token, httponly=True, secure=True, samesite="strict", max_age=3600)])  # @@T decoy cookie_flags httponly secure and samesite strict set together with a one hour lifetime

    @get("/web/pref/tarn/locale")  # @@R GET /web/pref/tarn/locale 1
    async def tarn_locale(self, request: Request) -> dict:
        return {"locale": "en"}

    @get("/web/ext/tern/remember")  # @@R GET /web/ext/tern/remember 1
    async def tern_remember(self, request: Request) -> Response:
        token = open_session(request.user.sess["uid"], request.user.sess["role"])
        return Response(None, status_code=204, cookies=[Cookie(key="sid", value=token)])  # @@T positive cookie_flags session cookie issued with no secure or httponly option

    @get("/web/ext/veery/trust")  # @@R GET /web/ext/veery/trust 1
    async def veery_trust(self, request: Request) -> Response:
        token = open_session(request.user.sess["uid"], request.user.sess["role"])
        return Response(None, status_code=204, cookies=[Cookie(key="trust", value=token, httponly=True, samesite="lax", max_age=86400)])  # @@T positive cookie_flags login token cookie travels over plain http because secure is not set


CONTROLLERS = [ProfileApi]
