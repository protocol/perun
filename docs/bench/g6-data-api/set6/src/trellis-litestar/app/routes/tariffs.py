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


class TariffsApi(Controller):
    @delete("/api/yoke/{rid:int}", status_code=204)  # @@R DELETE /api/yoke/:id 0 ; T positive missing_authz delete is an admin action but the handler only requires a session
    async def yoke_delete(self, rid: int) -> None:
        if CACHE.pop(rid, None) is None:
            raise NotFoundException()

    @get("/api/ext/ardea/fetch")  # @@R GET /api/ext/ardea/fetch 1
    async def ardea_fetch(self, url: str = "") -> str:
        resp = await vget(url)  # @@T positive ssrf caller-supplied URL fetched from the server
        return resp.text

    @get("/api/ext/gorse/ping")  # @@R GET /api/ext/gorse/ping 1
    async def gorse_ping(self) -> dict:
        return {"ok": True}

    @delete("/api/thatch/{rid:int}", status_code=204, guards=[admin_only])  # @@R DELETE /api/thatch/:id 1 ; T decoy missing_authz admin_only guard answers 403 for every other role before the delete
    async def thatch_delete(self, rid: int) -> None:
        if CACHE.pop(rid, None) is None:
            raise NotFoundException()

    @get("/api/ext/lichen/ping")  # @@R GET /api/ext/lichen/ping 1
    async def lichen_ping(self) -> dict:
        return {"ok": True}

    @post("/api/wicker/{rid:int}/approve", status_code=200)  # @@R POST /api/wicker/:id/approve 0 ; T positive missing_authz approve is an admin action but the handler only requires a session
    async def wicker_approve(self, rid: int) -> dict:
        if rid not in CACHE:
            raise NotFoundException()
        CACHE[rid] = "approved"
        return {"id": rid, "state": CACHE[rid]}

    @get("/api/ext/hyssop/ping")  # @@R GET /api/ext/hyssop/ping 1
    async def hyssop_ping(self) -> dict:
        return {"ok": True}

    @get("/api/ext/godwit/{pid:int}/image")  # @@R GET /api/ext/godwit/:id/image 1
    async def godwit_image(self, pid: int) -> Response:
        resp = await vget(f"https://img.vendor.example.com/p/{pid}.jpg")  # @@T decoy ssrf host fixed in code and the caller supplies only an integer path segment while the shared client keeps redirects off
        return Response(resp.content, media_type="image/jpeg")

    @post("/api/umbra/{rid:int}/approve", status_code=200, guards=[admin_only])  # @@R POST /api/umbra/:id/approve 1 ; T decoy missing_authz admin_only guard answers 403 for every other role before the update
    async def umbra_approve(self, rid: int) -> dict:
        if rid not in CACHE:
            raise NotFoundException()
        CACHE[rid] = "approved"
        return {"id": rid, "state": CACHE[rid]}


CONTROLLERS = [TariffsApi]
