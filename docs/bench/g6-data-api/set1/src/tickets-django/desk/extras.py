import hashlib
import json
import logging
import os

import requests
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

log = logging.getLogger("desk.extras")
HITS = {}


def allow(key, cap=20):
    HITS[key] = HITS.get(key, 0) + 1
    return HITS[key] <= cap


def sha(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:16]


def ask_llm(system, user):
    body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    return requests.post("https://llm.vendor.example.com/v1/chat", json=body, timeout=10).text

@require_http_methods(["GET"])
def search_tickets(request): # @@R GET /api/ext/search-tickets 1 ; T positive rate_limit search hits the table on every call with no limiter
    return JsonResponse({"q": request.GET.get("q", ""), "hits": []})

@require_http_methods(["GET"])
def list_tickets_all(request): # @@R GET /api/ext/list-tickets-all 1
    take = int(request.GET.get("limit", 0)) # @@T positive rate_limit page size taken from the caller with no cap or limiter
    return JsonResponse({"take": take})

# --
# --
# --
@require_http_methods(["POST"])
def login(request): # @@R POST /auth/login 0 public
    if not allow("login:" + request.META.get("REMOTE_ADDR", ""), 10): # @@T decoy rate_limit login is counted per client and answers 429 past the cap
        return HttpResponse(status=429)
    return JsonResponse({"ok": request.POST.get("pass") == os.environ.get("DESK_PW")})

# --
@csrf_exempt
@login_required
@require_http_methods(["POST"])
def change_email(request): # @@R POST /web/ext/change-email 1 ; T positive csrf csrf protection switched off on a cookie-session state change
    return JsonResponse({"updated": sha(request.POST.get("email"))})

@csrf_exempt
@login_required
@require_http_methods(["POST"])
def close_account(request): # @@R POST /web/ext/close-account 1 ; T positive csrf csrf protection switched off on a cookie-session delete
    return HttpResponse(status=204)

# --
# --
# --
@login_required
@require_http_methods(["POST"])
def change_phone(request): # @@R POST /web/ext/change-phone 1 ; T decoy csrf not csrf_exempt so CsrfViewMiddleware rejects the post without a valid token
    return HttpResponse(status=204)

# --
@login_required
@require_http_methods(["GET"])
def start_session(request): # @@R GET /web/ext/start-session 1
    resp = HttpResponse(status=204)
    resp.set_cookie("sid", sha(request.META.get("REMOTE_ADDR"))) # @@T positive cookie_flags session cookie without Secure HttpOnly or SameSite
    return resp

@login_required
@require_http_methods(["GET"])
def start_admin_session(request): # @@R GET /web/ext/start-admin-session 1
    resp = HttpResponse(status=204)
    resp.set_cookie("admin_sid", sha(request.headers.get("User-Agent")), httponly=True, path="/admin") # @@T positive cookie_flags HttpOnly set but Secure and SameSite missing
    return resp

# --
@login_required
@require_http_methods(["GET"])
def start_secure_session(request): # @@R GET /web/ext/start-secure-session 1
    resp = HttpResponse(status=204)
    resp.set_cookie("sid", sha(request.META.get("REMOTE_ADDR")), secure=True, httponly=True, samesite="Strict", max_age=3600) # @@T decoy cookie_flags Secure HttpOnly and SameSite all set
    return resp

# --
# --
# --
@require_http_methods(["POST"])
def signup(request): # @@R POST /auth/signup 0 public
    log.info("signup email=%s ssn=%s", request.POST.get("email"), request.POST.get("ssn")) # @@T positive pii_log raw email and national id written to the log
    return HttpResponse(status=201)

@require_http_methods(["POST"])
def pay_card(request): # @@R POST /api/ext/pay-card 1
    log.warning("charging card %s for %s", request.POST.get("card"), request.POST.get("name")) # @@T positive pii_log full card number and holder name logged
    return HttpResponse(status=202)

# --
# --
# --
@require_http_methods(["POST"])
def signup_hashed(request): # @@R POST /auth/signup-hashed 0 public
    log.info("signup user=%s", sha(request.POST.get("email"))) # @@T decoy pii_log only a truncated hash of the email is logged
    return HttpResponse(status=201)

# --
# --
class Requester:
    """Plain model-style record kept in the database."""

    ssn = "" # @@T positive pii_data national id stored unencrypted as a plain column
    email = ""
    dob = ""

@require_http_methods(["POST"])
def track_ticket(request): # @@R POST /api/ext/track-ticket 1
    requests.post("https://analytics.vendor.example.com/collect", json={"event": "ticket", "email": request.POST.get("email"), "phone": request.POST.get("phone")}, timeout=5) # @@T positive pii_data raw email and phone sent to a third-party analytics endpoint
    return HttpResponse(status=202)

# --
# --
# --
# --
SEED_REFS = [
    {"customer_ref": "cus_7f3a", "region": "EU", "vault_ref": "vault://pii/7f3a"}, # @@T decoy pii_data fixture carries opaque references only and the PII stays in the vault
    {"customer_ref": "cus_91bc", "region": "US", "vault_ref": "vault://pii/91bc"},
]

# --
@require_http_methods(["POST"])
def summarize_note(request): # @@R POST /api/ext/summarize-note 1
    note = request.POST.get("note", "")
    return HttpResponse(ask_llm("You may close tickets. Customer note: " + note, "summarize")) # @@T positive prompt_injection request text spliced into the system prompt of a model that can close tickets

@require_http_methods(["POST"])
def lookup_tool(request): # @@R POST /api/ext/lookup-tool 1
    args = '{"name":"lookup","arguments":{"ticket":"' + request.POST.get("ticket", "") + '"}}' # @@T positive prompt_injection request value concatenated into raw tool-call JSON
    return HttpResponse(requests.post("https://llm.vendor.example.com/v1/tools", data=args, timeout=10).text)

TOPICS = {"sla": "Explain the SLA tiers.", "queues": "Explain the queue routing."}


@require_http_methods(["POST"])
def explain_topic(request): # @@R POST /api/ext/explain-topic 1
    prompt = TOPICS.get(request.POST.get("topic"))
    if prompt is None:
        return HttpResponse(status=400)
    return HttpResponse(ask_llm("Answer briefly.", prompt)) # @@T decoy prompt_injection caller picks from a fixed allowlist and never supplies prompt text
