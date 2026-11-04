import json
import logging
import os
import secrets

import requests
from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, Response
from pydantic import BaseModel

from app.deps import cookie_user, current_user, member, require_admin
from app.store import ROWS, open_session
from app.util import Window, ask_model, ask_tool, owned_or_404

router = APIRouter()
log = logging.getLogger("fleet")
VENDOR = "https://dispatch.vendor.example.com"
VENDOR_KEY = os.environ.get("DISPATCH_KEY", "")
PIN = os.environ.get("FLEET_PIN", "")


class Label(BaseModel):
    label: str
export_window = Window(5, 60)


def export_limit(request: Request):
    if not export_window.allow(request.client.host):
        raise HTTPException(429)


@router.get("/api/ext/willow/{item_id}/image")  # @@R GET /api/ext/willow/{item_id}/image 1
def willow_image(item_id: int):
    upstream = requests.get(f"https://img.vendor.example.com/p/{item_id}.jpg", timeout=5, allow_redirects=False)  # @@T decoy ssrf host fixed in code and the caller supplies only an integer id with redirects off
    return Response(upstream.content[: 4 << 20], media_type="image/jpeg")


@router.get("/api/ext/juniper/{code}/rates")  # @@R GET /api/ext/juniper/{code}/rates 1
def juniper_rates(code: str):
    if len(code) != 2 or not code.isalpha():
        raise HTTPException(400)
    upstream = requests.get(f"{VENDOR}/v1/rates/{code}", headers={"X-Api-Key": VENDOR_KEY}, timeout=5)  # @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
    return upstream.json()


@router.get("/api/ext/falcon/{code}/stock")  # @@R GET /api/ext/falcon/{code}/stock 1
def falcon_stock(code: str):
    if len(code) != 2 or not code.isalpha():
        raise HTTPException(400)
    upstream = requests.get(f"{VENDOR}/v1/stock/{code}", headers={"X-Api-Key": VENDOR_KEY}, timeout=5)
    log.info("stock lookup code=%s status=%s", code, upstream.status_code)  # @@T decoy secret_in_log only the status and the validated code are logged
    return upstream.json()


@router.get("/api/ext/plover/export", dependencies=[Depends(export_limit)])  # @@R GET /api/ext/plover/export 1 ; T decoy rate_limit export_limit dependency counts calls per client address and answers 429 past five a minute
def plover_export():
    return [{"i": i, "label": f"plover-{i}"} for i in range(100000)]


@router.post("/api/ext/fjord/rotate-key")  # @@R POST /api/ext/fjord/rotate-key 1
def fjord_rotate_key(user=Depends(current_user)):
    key_id = secrets.token_hex(8)
    log.info("rotate user=%s domain=%s key_id=%s", user["uid"], user["email"].split("@")[-1], key_id[:6])  # @@T decoy pii_log the log line carries the numeric user id the email domain and a six character key id and no address or key
    return {"key_id": key_id}


@router.post("/api/ext/tarn/track")  # @@R POST /api/ext/tarn/track 1
def tarn_track(user=Depends(current_user)):
    requests.post("https://stats.vendor.example.com/v1/event", json={"event": "view", "uid": user["uid"]}, timeout=5)  # @@T decoy pii_data analytics payload carries the internal numeric id and no direct identifier
    return Response(status_code=204)


SEED_BLUFF = [{"label": "Sample route", "region": "north", "count": 3}]  # @@T decoy pii_data seed rows hold labels and counts and no person


@router.get("/api/ext/bluff/sample")  # @@R GET /api/ext/bluff/sample 1
def bluff_sample():
    return {"count": len(SEED_BLUFF)}


@router.post("/api/ext/moor/assist")  # @@R POST /api/ext/moor/assist 1
def moor_assist(note: str = Form()):
    return {"reply": ask_model([{"role": "system", "content": "You summarise dispatch notes and have no tools."}, {"role": "user", "content": note[:500]}])}  # @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message


@router.post("/api/ext/reef/lookup-tool")  # @@R POST /api/ext/reef/lookup-tool 1
def reef_lookup_tool(sku: str = Form()):
    return {"reply": ask_tool(json.dumps({"tool": "lookup", "arg": sku}))}  # @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
