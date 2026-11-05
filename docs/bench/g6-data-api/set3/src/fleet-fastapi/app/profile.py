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


@router.post("/web/ext/canyon/phone")  # @@R POST /web/ext/canyon/phone 1
def canyon_phone(request: Request, phone: str = Form(), x_csrf_token: str = Header(default="")):
    if not secrets.compare_digest(x_csrf_token, request.session.get("csrf", "-")):  # @@T decoy csrf per-session token compared in constant time and a missing header is rejected
        raise HTTPException(403)
    return {"updated": len(phone) <= 20}


@router.post("/web/ext/glacier/nickname")  # @@R POST /web/ext/glacier/nickname 1 ; T decoy csrf the framework session cookie is issued with SameSite strict so a cross-site post carries no session
def glacier_nickname(nickname: str = Form()):
    return {"updated": bool(nickname[:40])}


@router.get("/web/ext/ridge/rotate")  # @@R GET /web/ext/ridge/rotate 1
def ridge_rotate(request: Request, user=Depends(member)):
    request.session.clear()
    request.session["uid"] = user["uid"]  # @@T decoy cookie_flags session cookie attributes come from the SessionMiddleware config with https_only and same_site strict
    return Response(status_code=204)


@router.get("/web/ext/delta/keep")  # @@R GET /web/ext/delta/keep 1
def delta_keep(user=Depends(member)):
    resp = Response(status_code=204)
    resp.set_cookie("keep", secrets.token_hex(16), httponly=True, secure=True, samesite="strict", max_age=3600)  # @@T decoy cookie_flags httponly secure and samesite strict set together with a one hour lifetime
    return resp
