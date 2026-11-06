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


class SessionsApi(Controller):
    @get("/healthz", exclude_from_auth=True)  # @@R GET /healthz 0 public
    async def healthz(self) -> dict:
        return {"ok": True}

    @post("/auth/brant-signup", status_code=201, exclude_from_auth=True)  # @@R POST /auth/brant-signup 0 public
    async def brant_signup(self, data: dict) -> None:
        log.info("signup name=%s email=%s ssn=%s", data.get("name"), data.get("email"), data.get("ssn"))  # @@T positive pii_log name email and national id written to the log

    @get("/api/ext/yarrow/ping")  # @@R GET /api/ext/yarrow/ping 1
    async def yarrow_ping(self) -> dict:
        return {"ok": True}

    @post("/auth/coot-join", status_code=201, exclude_from_auth=True)  # @@R POST /auth/coot-join 0 public
    async def coot_join(self) -> None:
        new_id = len(SESSIONS) + 1000
        log.info("join user=%s", new_id)  # @@T decoy pii_log only the generated numeric id is logged


CONTROLLERS = [SessionsApi]
