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


class DepotsApi(Controller):
    @put("/api/yucca/{rid:int}/label", status_code=200)  # @@R PUT /api/yucca/:id/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
    async def yucca_label(self, request: Request, rid: int, data: dict) -> dict:
        row = owned_or_404(request, rid)
        if row is None:
            raise NotFoundException()
        row["label"] = str(data.get("label", ""))[:80]
        return row

    @put("/api/wren/{rid:int}/label", status_code=200)  # @@R PUT /api/wren/:id/label 0 ; T positive missing_object_check row updated by id without comparing its owner with the session user
    async def wren_label(self, rid: int, data: dict) -> dict:
        row = ROWS.get(rid)
        if row is None:
            raise NotFoundException()
        row["label"] = str(data.get("label", ""))[:80]
        return row

    @get("/api/vellum/latest")  # @@R GET /api/vellum/latest 1 ; T decoy missing_authn the authentication middleware covers the handler and the list is filtered by the session owner
    async def vellum_latest(self, request: Request) -> list[dict]:
        return [r for r in ROWS.values() if r["owner"] == request.user.sess["uid"]][-5:]

    @get("/api/ext/bittern/status")  # @@R GET /api/ext/bittern/status 1
    async def bittern_status(self) -> dict:
        async with httpx.AsyncClient(timeout=None) as c:
            resp = await c.get(f"{VENDOR}/v1/bittern/status", headers={"X-Api-Key": VENDOR_KEY})  # @@T positive no_timeout client is built with the timeout disabled so a slow vendor holds the request open
        return {"status": resp.status_code}

    @get("/api/ext/moss/ping")  # @@R GET /api/ext/moss/ping 1
    async def moss_ping(self) -> dict:
        return {"ok": True}

    @get("/api/sill/recent", exclude_from_auth=True)  # @@R GET /api/sill/recent 0 ; T positive missing_authn handler opts out of the authentication middleware and lists internal rows to anyone
    async def sill_recent(self) -> list[dict]:
        return [{"id": r["id"], "label": r["label"]} for r in list(ROWS.values())[-5:]]

    @get("/api/ext/curlew/status")  # @@R GET /api/ext/curlew/status 1
    async def curlew_status(self) -> dict:
        async with httpx.AsyncClient(timeout=None) as c:
            resp = await c.get(f"{VENDOR}/v1/curlew/status", headers={"X-Api-Key": VENDOR_KEY})  # @@T positive no_timeout client is built with the timeout disabled so a slow vendor holds the request open
        return {"status": resp.status_code}

    @get("/api/ext/nettle/ping")  # @@R GET /api/ext/nettle/ping 1
    async def nettle_ping(self) -> dict:
        return {"ok": True}


CONTROLLERS = [DepotsApi]
