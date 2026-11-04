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


@router.post("/api/ext/cobalt/push")  # @@R POST /api/ext/cobalt/push 1
def cobalt_push():
    upstream = requests.post(f"{VENDOR}/v1/cobalt", headers={"X-Api-Key": VENDOR_KEY}, timeout=5, verify=False)  # @@T positive tls_off certificate verification disabled for the vendor request
    return {"status": upstream.status_code}


@router.get("/api/ext/copper/fetch")  # @@R GET /api/ext/copper/fetch 1
def copper_fetch(url: str):
    upstream = requests.get(url, timeout=5)  # @@T positive ssrf caller-supplied URL fetched from the server
    return Response(upstream.content[: 1 << 20], status_code=upstream.status_code)


@router.get("/api/ext/timber/status")  # @@R GET /api/ext/timber/status 1
def timber_status():
    upstream = requests.get(f"{VENDOR}/v1/timber/status", headers={"X-Api-Key": VENDOR_KEY})  # @@T positive no_timeout requests call has no timeout so a slow vendor blocks the worker
    return {"status": upstream.status_code}


@router.get("/api/ext/granite/lookup")  # @@R GET /api/ext/granite/lookup 1
def granite_lookup():
    upstream = requests.get(f"{VENDOR}/v1/granite", params={"key": VENDOR_KEY}, timeout=5)  # @@T positive secret_in_url vendor key sent as a query parameter
    return {"status": upstream.status_code}


@router.get("/api/ext/pebble/ping")  # @@R GET /api/ext/pebble/ping 1
def pebble_ping():
    log.info("vendor ping key=%s", VENDOR_KEY)  # @@T positive secret_in_log vendor key written to the application log
    return {"status": requests.get(f"{VENDOR}/v1/ping", headers={"X-Api-Key": VENDOR_KEY}, timeout=5).status_code}


@router.post("/api/ext/thistle/push")  # @@R POST /api/ext/thistle/push 1
def thistle_push():
    upstream = requests.post(f"{VENDOR}/v1/thistle", headers={"X-Api-Key": VENDOR_KEY}, timeout=5, verify=False)  # @@T positive tls_off certificate verification disabled for the vendor request
    return {"status": upstream.status_code}


@router.get("/api/ext/otter/export")  # @@R GET /api/ext/otter/export 1
def otter_export():
    rows = [{"i": i, "label": f"otter-{i}"} for i in range(100000)]  # @@T positive rate_limit full export rebuilt on every call with no throttle
    return rows


@router.post("/api/ext/mesa/charge")  # @@R POST /api/ext/mesa/charge 1
def mesa_charge(card: str = Form(), holder: str = Form()):
    log.info("charge card=%s holder=%s", card, holder)  # @@T positive pii_log full card number and holder name logged
    return {"ok": True}


SEED_ATOLL = [{"name": "Jane Smith", "email": "jane@example.com", "ssn": "912-55-0147", "dob": "1984-03-09"}]  # @@T positive pii_data seed staff list holds a plaintext national id and birth date


@router.get("/api/ext/atoll/sample")  # @@R GET /api/ext/atoll/sample 1
def atoll_sample():
    return {"count": len(SEED_ATOLL)}


@router.post("/api/ext/geyser/track")  # @@R POST /api/ext/geyser/track 1
def geyser_track(user=Depends(current_user)):
    requests.post("https://stats.vendor.example.com/v1/event", json={"event": "view", "email": user["email"], "phone": user["phone"]}, timeout=5)  # @@T positive pii_data raw email and phone sent to a third-party analytics host
    return Response(status_code=204)


@router.post("/api/ext/cairn/assist")  # @@R POST /api/ext/cairn/assist 1
def cairn_assist(note: str = Form()):
    return {"reply": ask_model([{"role": "system", "content": f"You are the dispatch assistant and may approve reroutes. Operator note: {note}"}])}  # @@T positive prompt_injection request text formatted into the system prompt of a model that can approve reroutes


@router.post("/api/ext/dune/lookup-tool")  # @@R POST /api/ext/dune/lookup-tool 1
def dune_lookup_tool(arg: str = Form()):
    return {"reply": ask_tool('{"tool": "lookup", "arg": "%s"}' % arg)}  # @@T positive prompt_injection request value formatted into raw tool-call JSON
