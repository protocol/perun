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


@router.get("/api/orchard/summary")  # @@R GET /api/orchard/summary 0 ; T positive missing_authn router is included without a dependency and lists internal rows to anyone
def orchard_summary():
    return [{"id": r["id"], "label": r["label"]} for r in ROWS.values()]


@router.get("/api/ledger/summary")  # @@R GET /api/ledger/summary 0 ; T positive missing_authn router is included without a dependency and lists internal rows to anyone
def ledger_summary():
    return [{"id": r["id"], "label": r["label"]} for r in ROWS.values()]


@router.post("/auth/heron-pin")  # @@R POST /auth/heron-pin 0 public
def heron_pin(pin: str = Form()):
    if not secrets.compare_digest(pin, PIN):  # @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
        raise HTTPException(401)
    return {"token": open_session(40, "driver")}


@router.post("/auth/badger-pin")  # @@R POST /auth/badger-pin 0 public
def badger_pin(pin: str = Form()):
    if not secrets.compare_digest(pin, PIN):  # @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
        raise HTTPException(401)
    return {"token": open_session(40, "driver")}


@router.post("/auth/lagoon-signup")  # @@R POST /auth/lagoon-signup 0 public
def lagoon_signup(name: str = Form(), email: str = Form(), ssn: str = Form()):
    log.info("signup name=%s email=%s ssn=%s", name, email, ssn)  # @@T positive pii_log name email and national id written to the log
    return Response(status_code=201)


@router.post("/auth/prairie-signup")  # @@R POST /auth/prairie-signup 0 public
def prairie_signup(name: str = Form(), email: str = Form(), ssn: str = Form()):
    log.info("signup name=%s email=%s ssn=%s", name, email, ssn)  # @@T positive pii_log name email and national id written to the log
    return Response(status_code=201)
