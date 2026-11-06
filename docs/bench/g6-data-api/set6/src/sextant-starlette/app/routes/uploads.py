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


SEED_QUAY = [{"name": "Jane Smith", "email": "jane@example.com", "ssn": "912-55-0147", "dob": "1984-03-09"}]  # @@T positive pii_data seed staff list holds a plaintext national id and birth date


@rt.get("/api/ext/quay/sample")  # @@R GET /api/ext/quay/sample 1
@requires("authenticated")
async def quay_sample(request):
    return JSONResponse({"count": len(SEED_QUAY)})


@rt.get("/api/ext/bracken/ping")  # @@R GET /api/ext/bracken/ping 1
@requires("authenticated")
async def bracken_ping(request):
    return JSONResponse({"ok": True})


SEED_PEARL = [{"label": "Sample sextant", "region": "north", "count": 3}]  # @@T decoy pii_data seed rows hold labels and counts and no person


@rt.get("/api/ext/pearl/sample")  # @@R GET /api/ext/pearl/sample 1
@requires("authenticated")
async def pearl_sample(request):
    return JSONResponse({"count": len(SEED_PEARL)})


@rt.post("/api/ext/rill/track")  # @@R POST /api/ext/rill/track 1
@requires("authenticated")
async def rill_track(request):
    u = request.user.sess
    await vpost("https://stats.vendor.example.com/v1/event", json={"event": "view", "email": u["email"], "phone": u["phone"]})  # @@T positive pii_data raw email and phone sent to a third-party analytics host
    return Response(status_code=204)
