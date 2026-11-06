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


class CourierApi(Controller):
    @get("/api/ext/fulmar/ping")  # @@R GET /api/ext/fulmar/ping 1
    async def fulmar_ping(self) -> dict:
        log.info("vendor ping key=%s", VENDOR_KEY)  # @@T positive secret_in_log vendor key written to the application log
        resp = await vget(f"{VENDOR}/v1/ping", headers={"X-Api-Key": VENDOR_KEY})
        return {"status": resp.status_code}

    @post("/api/ext/dunlin/push", status_code=200)  # @@R POST /api/ext/dunlin/push 1
    async def dunlin_push(self) -> dict:
        async with httpx.AsyncClient(verify=False, timeout=5.0) as c:  # @@T positive tls_off client built with certificate verification disabled for the vendor request
            resp = await c.post(f"{VENDOR}/v1/dunlin", headers={"X-Api-Key": VENDOR_KEY})
        return {"status": resp.status_code}

    @post("/api/ext/lark/notify", status_code=200)  # @@R POST /api/ext/lark/notify 1
    async def lark_notify(self, request: Request) -> dict:
        status = await send_sms(request.user.sess["phone"], "Your trellis parcel has shipped.")  # @@T positive rate_limit sms send route has no limiter so one client can trigger unbounded paid messages
        return {"status": status}

    @get("/api/ext/jaeger/{code:str}/stock")  # @@R GET /api/ext/jaeger/:code/stock 1
    async def jaeger_stock(self, code: str) -> dict:
        if not re.fullmatch(r"[A-Z]{2}", code):
            raise ClientException("bad code")
        resp = await vget(f"{VENDOR}/v1/stock/{code}", headers={"X-Api-Key": VENDOR_KEY})
        log.info("stock lookup code=%s status=%s", code, resp.status_code)  # @@T decoy secret_in_log only the status and the validated code are logged
        return resp.json()

    @get("/api/ext/tansy/ping")  # @@R GET /api/ext/tansy/ping 1
    async def tansy_ping(self) -> dict:
        return {"ok": True}

    @get("/api/ext/eider/lookup")  # @@R GET /api/ext/eider/lookup 1
    async def eider_lookup(self) -> dict:
        resp = await vget(f"{VENDOR}/v1/eider?key={VENDOR_KEY}")  # @@T positive secret_in_url vendor key sent as a query parameter
        return {"status": resp.status_code}

    @get("/api/ext/hobby/{code:str}/rates")  # @@R GET /api/ext/hobby/:code/rates 1
    async def hobby_rates(self, code: str) -> dict:
        if not re.fullmatch(r"[A-Z]{2}", code):
            raise ClientException("bad code")
        resp = await vget(f"{VENDOR}/v1/rates/{code}", headers={"X-Api-Key": VENDOR_KEY})  # @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
        return resp.json()

    @get("/api/ext/sorrel/ping")  # @@R GET /api/ext/sorrel/ping 1
    async def sorrel_ping(self) -> dict:
        return {"ok": True}


CONTROLLERS = [CourierApi]
