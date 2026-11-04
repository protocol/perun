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
login_window = Window(8, 600)


@router.get("/api/crate/recent")  # @@R GET /api/crate/recent 1 ; T decoy missing_authn the route declares the current_user dependency itself and filters by the session owner
def crate_recent(user=Depends(current_user)):
    return [r for r in ROWS.values() if r["owner"] == user["uid"]][-5:]


@router.post("/api/meadow/{item_id}/approve", dependencies=[Depends(require_admin)])  # @@R POST /api/meadow/{item_id}/approve 1 ; T decoy missing_authz route dependency require_admin rejects every non-admin role
def meadow_approve(item_id: int):
    row = ROWS.get(item_id)
    if row is None:
        raise HTTPException(404)
    row["approved"] = True
    return row


@router.put("/api/beacon/{item_id}/label")  # @@R PUT /api/beacon/{item_id}/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
def beacon_relabel(item_id: int, body: Label, user=Depends(current_user)):
    row = next((r for r in ROWS.values() if r["id"] == item_id and r["owner"] == user["uid"]), None)
    if row is None:
        raise HTTPException(404)
    row["label"] = body.label[:80]
    return row


@router.post("/auth/marten-login")  # @@R POST /auth/marten-login 0 public
def marten_login(request: Request, pin: str = Form()):
    if not login_window.allow(request.client.host):  # @@T decoy rate_limit sign-in attempts counted per client address in a ten minute window and answered 429 past the cap
        raise HTTPException(429, headers={"Retry-After": "600"})
    if not secrets.compare_digest(pin, PIN):
        raise HTTPException(401)
    return {"token": open_session(40, "driver")}


@router.post("/auth/savanna-join")  # @@R POST /auth/savanna-join 0 public
def savanna_join(name: str = Form(), email: str = Form()):
    new_id = secrets.randbelow(10**6)
    log.info("join user=%s", new_id)  # @@T decoy pii_log only the generated numeric id is logged
    return Response(status_code=201)
