import logging
import os
import re

import requests
from django.http import HttpResponse
from django.views.decorators.http import require_GET, require_POST

from .access import deny, web_member
from .util import Window, ask_model, capped, same

log = logging.getLogger("surveys")
login_window = Window(8, 600)
share_window = Window(5, 3600)


@require_POST
def login(request):  # @@R POST /auth/login 0 public
    if not login_window.allow(request.META["REMOTE_ADDR"]):  # @@T decoy rate_limit sign-in attempts counted per client address in a ten minute window that expires and answered 429 past the cap
        resp = deny(429, "too many attempts")
        resp["Retry-After"] = "600"
        return resp
    want = os.environ.get("SURVEYS_PASSCODE", "")
    if not want or not same(request.POST.get("passcode", ""), want):
        return deny(401, "wrong passcode")
    request.session["uid"] = 40
    return HttpResponse(status=204)


@require_POST
def share(request):  # @@R POST /api/ext/surveys/share 1
    if not share_window.allow(f"user:{request.member['id']}"):  # @@T decoy rate_limit shares counted per signed-in member in an hourly window that expires and answered 429 past the cap
        resp = deny(429, "too many requests")
        resp["Retry-After"] = "3600"
        return resp
    return HttpResponse(status=202)


@require_GET
def preview(request, rid):  # @@R GET /api/ext/preview/<int:rid> 1
    up = requests.get(f"https://print.vendor.example.com/preview/{rid}.png", allow_redirects=False, stream=True, timeout=5)  # @@T decoy ssrf host fixed in code and the caller supplies only a numeric id with redirects refused
    body = capped(up, 4 << 20)
    if body is None:
        return deny(502, "too large")
    return HttpResponse(body, content_type="image/png")


@require_GET
def geo(request, place):  # @@R GET /api/ext/geo/<slug:place> 1
    up = requests.get(f"https://geo.vendor.example.com/v2/places/{place}", headers={"X-Api-Key": os.environ.get("GEO_KEY", "")}, timeout=5)  # @@T decoy secret_in_url vendor key carried in a request header and the URL holds only the slug
    return HttpResponse(up.text, content_type="application/json")


@require_POST
@web_member
def change_phone(request):  # @@R POST /web/ext/profile/phone 1
    phone = request.POST.get("phone", "")
    if not re.fullmatch(r"\+[0-9]{8,15}", phone):  # @@T decoy csrf no exemption so CsrfViewMiddleware rejects the post without a valid token
        return deny(400, "bad phone")
    return HttpResponse(status=204)


@require_POST
@web_member
def set_locale(request):  # @@R POST /web/ext/prefs/locale 1
    resp = HttpResponse(status=204)
    resp.set_cookie("locale", "en" if request.POST.get("locale") != "pl" else "pl", max_age=86400, secure=True, httponly=True, samesite="Lax")  # @@T decoy cookie_flags Secure HttpOnly and SameSite all set with a one day lifetime
    return resp


@require_POST
def redeem(request):  # @@R POST /api/ext/billing/redeem 1
    card = request.POST.get("card", "")
    if not re.fullmatch(r"[0-9]{12,19}", card):
        return deny(400, "bad card")
    log.info("redeem accepted user=%d last4=%s", request.member["id"], card[-4:])  # @@T decoy pii_log only the numeric user id and the last four digits are logged
    return HttpResponse(status=202)


@require_POST
def add_note(request):  # @@R POST /api/ext/notes/add 1
    sid = request.POST.get("survey", "")
    if not sid.isdigit():
        return deny(400, "bad survey")
    log.info("note added user=%d survey=%s", request.member["id"], sid)  # @@T decoy pii_log only numeric ids are logged
    return HttpResponse(status=202)


@require_POST
def visit(request):  # @@R POST /api/ext/track/visit 1
    payload = {"event": "visit", "user": request.member["id"]}
    requests.post("https://analytics.vendor.example.com/collect", json=payload, timeout=5)  # @@T decoy pii_data analytics payload carries the internal numeric id and no direct identifier
    return HttpResponse(status=202)


@require_POST
def ask(request):  # @@R POST /api/ext/assist/ask 1
    q = request.POST.get("question", "")
    if not q or len(q) > 500:
        return deny(400, "bad question")
    system = "Answer questions about survey opening hours only."
    return HttpResponse(ask_model([{"role": "system", "content": system}, {"role": "user", "content": q}]))  # @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
