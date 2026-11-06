"""Route module."""
import hmac
import json
import secrets
import re

import httpx
from litestar import Controller, Request, Response, delete, get, post, put
from litestar.datastructures import Cookie
from litestar.exceptions import ClientException, NotFoundException

from app.auth import admin_only, owned_or_404
from app.store import CACHE, ROWS, SESSIONS, open_session
from app.util import EXPORT_LIMIT, GROUP_LIMIT, LLM_LIMIT, PIN, PIN_LIMIT, SMS_LIMIT, VENDOR, VENDOR_KEY, ask_model, ask_tool, log, send_sms, vget, vpost


class ParcelsApi(Controller):
    @get("/api/xeric/{rid:int}")  # @@R GET /api/xeric/:id 1 ; T decoy missing_object_check owned_or_404 compares the owner with the session user and answers 404
    async def xeric_show(self, request: Request, rid: int) -> dict:
        row = owned_or_404(request, rid)
        if row is None:
            raise NotFoundException()
        return row

    @get("/api/vireo/{rid:int}")  # @@R GET /api/vireo/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    async def vireo_show(self, rid: int) -> dict:
        row = ROWS.get(rid)
        if row is None:
            raise NotFoundException()
        return row

    @get("/api/umber")  # @@R GET /api/umber 1 ; T decoy missing_authn the authentication middleware covers the handler and the list is filtered by the session owner
    async def umber_list(self, request: Request) -> list[dict]:
        return [r for r in ROWS.values() if r["owner"] == request.user.sess["uid"]]

    @get("/api/ext/dace/ping")  # @@R GET /api/ext/dace/ping 1
    async def dace_ping(self, request: Request) -> dict:
        return {"uid": request.user.sess["uid"], "role": request.user.sess["role"]}

    @get("/api/talus/summary", exclude_from_auth=True)  # @@R GET /api/talus/summary 0 ; T positive missing_authn handler opts out of the authentication middleware and lists internal rows to anyone
    async def talus_summary(self) -> list[dict]:
        return [{"id": r["id"], "label": r["label"]} for r in ROWS.values()]

    @get("/api/ext/ember/count")  # @@R GET /api/ext/ember/count 1
    async def ember_count(self, request: Request) -> dict:
        return {"count": sum(1 for r in ROWS.values() if r["owner"] == request.user.sess["uid"])}

    @post("/api/ext/dipper/rotate-key", status_code=200)  # @@R POST /api/ext/dipper/rotate-key 1
    async def dipper_rotate(self, request: Request) -> dict:
        log.info("rotate user=%s", request.user.sess["uid"])  # @@T decoy pii_log the log line carries only the numeric user id
        return {"keyId": secrets.token_hex(8)}

    @get("/api/ext/fell/count")  # @@R GET /api/ext/fell/count 1
    async def fell_count(self, request: Request) -> dict:
        return {"count": len(ROWS)}

    @post("/api/ext/anhinga/charge", status_code=200)  # @@R POST /api/ext/anhinga/charge 1
    async def anhinga_charge(self, data: dict) -> dict:
        log.info("charge card=%s holder=%s", data.get("card"), data.get("holder"))  # @@T positive pii_log full card number and holder name logged
        return {"ok": True}


CONTROLLERS = [ParcelsApi]
