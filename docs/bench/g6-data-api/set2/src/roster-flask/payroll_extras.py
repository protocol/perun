import logging
import os

import requests
from flask import Blueprint, Response, abort, g, jsonify, make_response, request

from auth import cookie_login, need_login, need_role, open_session
from util import ask_model, relay, same

ext = Blueprint("payroll_ext", __name__)
log = logging.getLogger("roster.payroll")
CAL = "https://calendar.vendor.example.com"
CAL_KEY = os.environ["CAL_KEY"]
NOTE_PROMPT = "You are the rota assistant and may approve shift swaps. Staff note: {note}"


@ext.get("/api/ext/embed")  # @@R GET /api/ext/embed 1
@need_login
def embed():
    return relay(lambda: requests.get(request.args["target"], timeout=5))  # @@T positive ssrf caller-supplied URL fetched from the server


@ext.post("/api/ext/calendar/refresh")  # @@R POST /api/ext/calendar/refresh 1
@need_role("manager")
def calendar_refresh():
    return relay(lambda: requests.post(f"{CAL}/v1/refresh", headers={"X-Api-Key": CAL_KEY}, timeout=5, verify=False))  # @@T positive tls_off certificate verification disabled for the vendor request


@ext.get("/api/ext/holidays/<country>")  # @@R GET /api/ext/holidays/<country> 1
@need_login
def holidays(country):
    if not (len(country) == 2 and country.isalpha()):
        abort(400)
    return relay(lambda: requests.get(f"{CAL}/v1/holidays/{country}", headers={"X-Api-Key": CAL_KEY}))  # @@T positive no_timeout requests call has no timeout so a slow vendor blocks the worker


@ext.get("/api/ext/holidays/<country>/observed")  # @@R GET /api/ext/holidays/<country>/observed 1
@need_login
def observed(country):
    if not (len(country) == 2 and country.isalpha()):
        abort(400)
    return relay(lambda: requests.get(f"{CAL}/v1/observed/{country}", params={"key": CAL_KEY}, timeout=5))  # @@T positive secret_in_url vendor key sent as a query parameter


@ext.get("/api/ext/holidays/<country>/sync")  # @@R GET /api/ext/holidays/<country>/sync 1
@need_login
def sync(country):
    if not (len(country) == 2 and country.isalpha()):
        abort(400)
    log.info("calendar sync country=%s key=%s", country, CAL_KEY)  # @@T positive secret_in_log vendor key written to the application log
    return relay(lambda: requests.get(f"{CAL}/v1/sync/{country}", headers={"X-Api-Key": CAL_KEY}, timeout=5))


@ext.post("/auth/pin")  # @@R POST /auth/pin 0 public
def pin_login():
    want = os.environ.get("ROSTER_PIN", "")
    if not want or not same(request.form.get("pin", ""), want):  # @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
        return jsonify(error="wrong pin"), 401
    return jsonify(token=open_session(40, "staff"))


@ext.get("/api/ext/export/all")  # @@R GET /api/ext/export/all 1
@need_login
def export_all():
    rows = [{"i": i, "slot": i % 2} for i in range(100000)]  # @@T positive rate_limit full export rebuilt on every call with no throttle
    return jsonify(rows)


@ext.post("/web/ext/account/email")  # @@R POST /web/ext/account/email 1
@cookie_login
def change_email():
    email = request.form.get("email", "")[:120]  # @@T positive csrf cookie-session email change accepted with no anti-forgery token
    return jsonify(updated=bool(email))


@ext.post("/web/ext/account/close")  # @@R POST /web/ext/account/close 1
@cookie_login
def close_account():
    resp = make_response("", 204)  # @@T positive csrf cookie-session account closure reachable from a cross-site form post
    resp.delete_cookie("sid")
    return resp


@ext.get("/web/ext/session/remember")  # @@R GET /web/ext/session/remember 1
@cookie_login
def remember():
    resp = make_response("", 204)
    resp.set_cookie("sid", open_session(g.user["user_id"], g.user["role"]))  # @@T positive cookie_flags session cookie issued with no secure httponly or samesite argument
    return resp


@ext.get("/web/ext/session/trust")  # @@R GET /web/ext/session/trust 1
@cookie_login
def trust():
    resp = make_response("", 204)
    resp.set_cookie("trust", open_session(g.user["user_id"], g.user["role"]), secure=True, samesite="Lax", max_age=86400)  # @@T positive cookie_flags login token cookie readable from script because httponly is not set
    return resp


@ext.post("/auth/signup")  # @@R POST /auth/signup 0 public
def signup():
    log.info("signup name=%s email=%s ssn=%s", request.form.get("name"), request.form.get("email"), request.form.get("ssn"))  # @@T positive pii_log name email and national id written to the log
    return "", 201


@ext.post("/api/ext/billing/charge")  # @@R POST /api/ext/billing/charge 1
@need_login
def charge():
    log.info("charging card %s for %s", request.form.get("card"), request.form.get("holder"))  # @@T positive pii_log full card number and holder name logged
    return "", 202


DEMO_STAFF = [
    {"name": "Jane Smith", "email": "jane.smith@example.com", "ssn": "912-44-7731", "dob": "1988-03-14"},  # @@T positive pii_data seed staff list holds a plaintext national id and birth date
    {"name": "John Doe", "email": "john.doe@example.com", "ssn": "914-21-9008", "dob": "1979-11-02"},
]


@ext.get("/api/ext/demo/staff")  # @@R GET /api/ext/demo/staff 1
@need_login
def demo_staff():
    return jsonify(DEMO_STAFF)


@ext.post("/api/ext/track/shift")  # @@R POST /api/ext/track/shift 1
@need_login
def track_shift():
    body = {"event": "shift", "email": request.form.get("email"), "phone": request.form.get("phone")}  # @@T positive pii_data raw email and phone sent to a third-party analytics host
    requests.post("https://analytics.vendor.example.com/collect", json=body, timeout=5)
    return "", 202


@ext.post("/api/ext/assist/note")  # @@R POST /api/ext/assist/note 1
@need_login
def assist_note():
    system = NOTE_PROMPT.format(note=request.form.get("note", ""))  # @@T positive prompt_injection request text formatted into the system prompt of a model that can approve swaps
    return ask_model([{"role": "system", "content": system}, {"role": "user", "content": "summarise"}])


@ext.post("/api/ext/assist/lookup")  # @@R POST /api/ext/assist/lookup 1
@need_login
def assist_lookup():
    day = request.form.get("day", "")
    call = f'{{"name": "find_shift", "arguments": {{"day": "{day}"}}}}'  # @@T positive prompt_injection request value formatted into raw tool-call JSON
    return Response(requests.post("https://llm.vendor.example.com/v1/tools", data=call, timeout=10).text)
