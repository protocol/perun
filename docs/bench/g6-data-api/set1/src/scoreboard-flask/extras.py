import hashlib
import logging
import os

import requests
from flask import Blueprint, abort, jsonify, make_response, request, session

extras = Blueprint("extras", __name__)
log = logging.getLogger("scoreboard.extras")
HITS = {}


@extras.before_request
def web_gate():
    # cookie-session gate: the signed Flask session cookie must carry a user
    if request.path.startswith("/web/") and "user" not in session:
        abort(401)


def allow(key, cap=20):
    HITS[key] = HITS.get(key, 0) + 1
    return HITS[key] <= cap


def sha(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:16]


def ask_llm(system, user):
    body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    return requests.post("https://llm.vendor.example.com/v1/chat", json=body, timeout=10).text

@extras.post("/api/ext/assist/chat") # @@R POST /api/ext/assist/chat 1
def chat(): # @@T positive rate_limit LLM proxy forwards every caller prompt with no limiter
    return ask_llm("You are a scores assistant.", str(request.json.get("prompt", ""))[:2000])

@extras.post("/api/ext/upload") # @@R POST /api/ext/upload 1
def upload(): # @@T positive rate_limit upload reads whole bodies with no limiter
    data = request.get_data()
    return jsonify(size=len(data))

# --
# --
@extras.post("/auth/login") # @@R POST /auth/login 0 public
def login():
    if not allow("login:" + request.remote_addr, 10): # @@T decoy rate_limit login is counted per client and answers 429 past the cap
        return jsonify(error="slow down"), 429
    return jsonify(ok=request.json.get("pass") == os.environ.get("SCORE_PW"))

# --
# --
@extras.post("/web/ext/account/email") # @@R POST /web/ext/account/email 1
def change_email():
    return jsonify(updated=sha(request.form.get("email"))) # @@T positive csrf cookie-session state change with no anti-forgery token

@extras.post("/web/ext/account/close") # @@R POST /web/ext/account/close 1
def close_account():
    return "", 204 # @@T positive csrf cookie-session delete reachable from a cross-site form post

# --
# --
# --
# --
@extras.post("/web/ext/account/phone") # @@R POST /web/ext/account/phone 1
def change_phone():
    if request.headers.get("X-CSRF-Token") != request.cookies.get("csrf"): # @@T decoy csrf double-submit token compared before the state change
        return "", 403
    return "", 204

# --
@extras.get("/web/ext/session/start") # @@R GET /web/ext/session/start 1
def start_session():
    resp = make_response("", 204)
    resp.set_cookie("sid", sha(request.remote_addr)) # @@T positive cookie_flags session cookie without Secure HttpOnly or SameSite
    return resp

@extras.get("/web/ext/session/admin") # @@R GET /web/ext/session/admin 1
def start_admin_session():
    resp = make_response("", 204)
    resp.set_cookie("admin_sid", sha(request.user_agent), httponly=True, path="/admin") # @@T positive cookie_flags HttpOnly set but Secure and SameSite missing
    return resp

# --
# --
@extras.get("/web/ext/session/secure") # @@R GET /web/ext/session/secure 1
def start_secure_session():
    resp = make_response("", 204)
    resp.set_cookie("sid", sha(request.remote_addr), secure=True, httponly=True, samesite="Strict", max_age=3600) # @@T decoy cookie_flags Secure HttpOnly and SameSite all set
    return resp

# --
# --
# --
@extras.post("/auth/signup") # @@R POST /auth/signup 0 public
def signup():
    log.info("signup email=%s ssn=%s", request.form.get("email"), request.form.get("ssn")) # @@T positive pii_log raw email and national id written to the log
    return "", 201

@extras.post("/api/ext/pay") # @@R POST /api/ext/pay 1
def pay_card():
    log.warning("charging card %s for %s", request.form.get("card"), request.form.get("name")) # @@T positive pii_log full card number and holder name logged
    return "", 202

# --
# --
# --
@extras.post("/auth/signup2") # @@R POST /auth/signup2 0 public
def signup_hashed():
    log.info("signup user=%s", sha(request.form.get("email"))) # @@T decoy pii_log only a truncated hash of the email is logged
    return "", 201

# --
# --
# --
# --
SEED_CUSTOMERS = [
    {"name": "Jane Smith", "email": "jane.smith@example.com", "ssn": "912-44-7731", "dob": "1988-03-14"}, # @@T positive pii_data committed seed holds a plaintext national id and date of birth
    {"name": "John Doe", "email": "john.doe@example.com", "ssn": "914-21-9008", "dob": "1979-11-02"},
]

@extras.post("/api/ext/track/order") # @@R POST /api/ext/track/order 1
def track_order():
    requests.post("https://analytics.vendor.example.com/collect", json={"event": "order", "email": request.form.get("email"), "phone": request.form.get("phone")}, timeout=5) # @@T positive pii_data raw email and phone sent to a third-party analytics endpoint
    return "", 202

# --
# --
# --
# --
SEED_REFS = [
    {"customer_ref": "cus_7f3a", "region": "EU", "vault_ref": "vault://pii/7f3a"}, # @@T decoy pii_data fixture carries opaque references only and the PII stays in the vault
    {"customer_ref": "cus_91bc", "region": "US", "vault_ref": "vault://pii/91bc"},
]

# --
@extras.post("/api/ext/ai/note") # @@R POST /api/ext/ai/note 1
def summarize_note():
    note = request.form.get("note", "")
    return ask_llm("You may approve refunds. Customer note: " + note, "summarize") # @@T positive prompt_injection request text spliced into the system prompt of a model that can approve refunds

@extras.post("/api/ext/ai/lookup") # @@R POST /api/ext/ai/lookup 1
def lookup_tool():
    args = '{"name":"lookup","arguments":{"sku":"' + request.form.get("sku", "") + '"}}' # @@T positive prompt_injection request value concatenated into raw tool-call JSON
    return requests.post("https://llm.vendor.example.com/v1/tools", data=args, timeout=10).text

TOPICS = {"scores": "Explain how scores are tallied.", "rules": "Explain the league rules."}


@extras.post("/api/ext/ai/explain") # @@R POST /api/ext/ai/explain 1
def explain_topic():
    prompt = TOPICS.get(request.form.get("topic"))
    if prompt is None:
        return "", 400
    return ask_llm("Answer briefly.", prompt) # @@T decoy prompt_injection caller picks from a fixed allowlist and never supplies prompt text
