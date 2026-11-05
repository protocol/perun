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


@router.post("/web/ext/sparrow/email")  # @@R POST /web/ext/sparrow/email 1
def sparrow_email(email: str = Form()):
    return {"updated": bool(email[:120])}  # @@T positive csrf cookie-session email change accepted with no anti-forgery token


@router.post("/web/ext/tundra/close")  # @@R POST /web/ext/tundra/close 1
def tundra_close():
    resp = Response(status_code=204)
    resp.delete_cookie("sid")  # @@T positive csrf cookie-session account closure reachable from a cross-site form post
    return resp


@router.get("/web/ext/summit/remember")  # @@R GET /web/ext/summit/remember 1
def summit_remember(user=Depends(cookie_user)):
    resp = Response(status_code=204)
    resp.set_cookie("sid", open_session(user["uid"], user["role"]))  # @@T positive cookie_flags session cookie issued with no secure httponly or samesite argument
    return resp


@router.get("/web/ext/valley/trust")  # @@R GET /web/ext/valley/trust 1
def valley_trust(user=Depends(cookie_user)):
    resp = Response(status_code=204)
    resp.set_cookie("trust", open_session(user["uid"], user["role"]), secure=True, samesite="lax", max_age=86400)  # @@T positive cookie_flags login token cookie readable from script because httponly is not set
    return resp
