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


class IntakeApi(Controller):
    SEED_FANTAIL = [{"name": "Jane Smith", "email": "jane@example.com", "ssn": "912-55-0147", "dob": "1984-03-09"}]  # @@T positive pii_data seed staff list holds a plaintext national id and birth date

    @get("/api/ext/fantail/sample")  # @@R GET /api/ext/fantail/sample 1
    async def fantail_sample(self) -> dict:
        return {"count": len(self.SEED_FANTAIL)}

    @get("/api/ext/olive/ping")  # @@R GET /api/ext/olive/ping 1
    async def olive_ping(self) -> dict:
        return {"ok": True}

    @post("/api/ext/knot/track", status_code=204)  # @@R POST /api/ext/knot/track 1
    async def knot_track(self) -> None:
        await vpost("https://stats.vendor.example.com/v1/event", json={"event": "view"})  # @@T decoy pii_data analytics payload is a constant event name with no user identifier

    SEED_JACANA = [{"label": "Sample trellis", "region": "north", "count": 3}]  # @@T decoy pii_data seed rows hold labels and counts and no person

    @get("/api/ext/jacana/sample")  # @@R GET /api/ext/jacana/sample 1
    async def jacana_sample(self) -> dict:
        return {"count": len(self.SEED_JACANA)}

    @post("/api/ext/grebe/track", status_code=204)  # @@R POST /api/ext/grebe/track 1
    async def grebe_track(self, request: Request) -> None:
        u = request.user.sess
        await vpost("https://stats.vendor.example.com/v1/event", json={"event": "view", "email": u["email"], "phone": u["phone"]})  # @@T positive pii_data raw email and phone sent to a third-party analytics host

    @post("/api/ext/harrier/track", status_code=204)  # @@R POST /api/ext/harrier/track 1
    async def harrier_track(self, data: dict) -> None:
        await vpost("https://stats.vendor.example.com/v1/profile", json={"event": "signup", "name": data.get("name"), "dob": data.get("dob")})  # @@T positive pii_data full name and birth date sent to a third-party analytics host

    @get("/api/ext/sumac/ping")  # @@R GET /api/ext/sumac/ping 1
    async def sumac_ping(self) -> dict:
        return {"ok": True}


CONTROLLERS = [IntakeApi]
