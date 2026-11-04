import hmac
import json
import logging
import os
import re

import requests
from flask import Blueprint, abort, g, jsonify, make_response, request

from auth import cookie_login, need_login, open_session, SESSIONS
from util import Window, ask_model, capped, relay, same

ext = Blueprint("badge_ext", __name__)
log = logging.getLogger("roster.badge")
CAL = "https://calendar.vendor.example.com"
CAL_KEY = os.environ["CAL_KEY"]
COUNTRY = re.compile(r"^[A-Z]{2}$")
SKU = re.compile(r"^[A-Z0-9-]{3,20}$")
CARD = re.compile(r"^[0-9]{12,19}$")
login_window = Window(8, 600)


def csrf_ok():
    return hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), g.user["csrf"])


@ext.post("/auth/login")  # @@R POST /auth/login 0 public
def login():
    if not login_window.allow(request.remote_addr):  # @@T decoy rate_limit sign-in attempts counted per client address in a ten minute window and answered 429 past the cap
        return jsonify(error="too many attempts"), 429, {"Retry-After": "600"}
    want = os.environ.get("ROSTER_PASSCODE", "")
    if not want or not same(request.form.get("passcode", ""), want):
        return jsonify(error="wrong passcode"), 401
    return jsonify(token=open_session(41, "manager"))


@ext.get("/api/ext/photo/<int:photo_id>")  # @@R GET /api/ext/photo/<int:photo_id> 1
@need_login
def photo(photo_id):
    try:
        upstream = requests.get(f"https://img.vendor.example.com/p/{photo_id}.jpg", timeout=5, stream=True, allow_redirects=False)  # @@T decoy ssrf host fixed in code and the caller supplies only an integer id with redirects off
    except requests.RequestException:
        return "", 502
    body, status = capped(upstream, 4 << 20)
    return body, status, {"Content-Type": "image/jpeg"}


@ext.get("/api/ext/holidays/<country>/history")  # @@R GET /api/ext/holidays/<country>/history 1
@need_login
def history(country):
    if not COUNTRY.match(country):
        abort(400)
    return relay(lambda: requests.get(f"{CAL}/v1/history/{country}", headers={"X-Api-Key": CAL_KEY}, timeout=5))  # @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated country code


@ext.get("/api/ext/holidays/<country>/digest")  # @@R GET /api/ext/holidays/<country>/digest 1
@need_login
def digest(country):
    if not COUNTRY.match(country):
        abort(400)
    try:
        upstream = requests.get(f"{CAL}/v1/digest/{country}", headers={"X-Api-Key": CAL_KEY}, timeout=5)
    except requests.RequestException:
        return "", 502
    log.info("digest upstream status=%s country=%s", upstream.status_code, country)  # @@T decoy secret_in_log only the status code and the validated country code are logged
    return upstream.content[: 1 << 20], upstream.status_code


@ext.post("/web/ext/account/phone")  # @@R POST /web/ext/account/phone 1
@cookie_login
def change_phone():
    if not csrf_ok():  # @@T decoy csrf per-session token compared in constant time and a missing header is rejected
        abort(403)
    if len(request.form.get("phone", "")) > 20:
        abort(400)
    return "", 204


@ext.post("/web/ext/session/rotate")  # @@R POST /web/ext/session/rotate 1
@cookie_login
def rotate():
    if not csrf_ok():
        abort(403)
    SESSIONS.pop(request.cookies.get("sid"), None)
    resp = make_response("", 204)
    resp.set_cookie("sid", open_session(g.user["user_id"], g.user["role"]), httponly=True, secure=True, samesite="Lax", max_age=3600, path="/")  # @@T decoy cookie_flags httponly secure and samesite Lax set together with a one hour lifetime
    return resp


@ext.post("/web/ext/session/end")  # @@R POST /web/ext/session/end 1
@cookie_login
def end():
    if not csrf_ok():
        abort(403)
    SESSIONS.pop(request.cookies.get("sid"), None)
    resp = make_response("", 204)
    resp.delete_cookie("sid", path="/", httponly=True, secure=True, samesite="Lax")  # @@T decoy cookie_flags expiry cookie keeps every attribute and the server session is dropped first
    return resp


@ext.post("/api/ext/billing/settle")  # @@R POST /api/ext/billing/settle 1
@need_login
def settle():
    card = request.form.get("card", "")
    if not CARD.match(card):
        abort(400)
    log.info("payment accepted user=%s last4=%s", g.user["user_id"], card[-4:])  # @@T decoy pii_log only the numeric user id and the last four digits are logged
    return "", 202


@ext.post("/api/ext/track/visit")  # @@R POST /api/ext/track/visit 1
@need_login
def track_visit():
    body = {"event": "visit", "user": g.user["user_id"]}  # @@T decoy pii_data analytics payload carries the internal numeric id and no direct identifier
    requests.post("https://analytics.vendor.example.com/collect", json=body, timeout=5)
    return "", 202


@ext.post("/api/ext/assist/question")  # @@R POST /api/ext/assist/question 1
@need_login
def question():
    q = request.form.get("question", "")
    if not q or len(q) > 500:
        abort(400)
    return ask_model([{"role": "system", "content": "Answer questions about shift times and rota rules only."}, {"role": "user", "content": q}])  # @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message


@ext.post("/api/ext/assist/part")  # @@R POST /api/ext/assist/part 1
@need_login
def part():
    sku = request.form.get("sku", "")
    if not SKU.match(sku):
        abort(400)
    call = json.dumps({"name": "find_badge", "arguments": {"sku": sku}})  # @@T decoy prompt_injection tool name fixed and the validated sku is JSON-encoded as data
    return requests.post("https://llm.vendor.example.com/v1/tools", data=call, timeout=10).text
