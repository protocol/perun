import logging
import os
import re
import secrets

import requests
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import store
from .access import deny, require_role, web_member
from .util import ask_model, same

log = logging.getLogger("surveys")
CATALOG = "https://catalog.vendor.example.com"
FORECAST = "https://forecast.vendor.example.com"
RADAR = "https://radar.vendor.example.com"
SMS = "https://sms.vendor.example.com/v1/send"


def key(name):
    return os.environ.get(name, "")


@require_GET
def embed(request):  # @@R GET /api/ext/embed 1
    up = requests.get(request.GET.get("target", ""), timeout=5)  # @@T positive ssrf caller-supplied URL fetched from the server
    return HttpResponse(up.text, content_type="text/html")


@require_POST
@require_role("admin")
def refresh_catalog(request):  # @@R POST /api/ext/catalog/refresh 1
    up = requests.get(f"{CATALOG}/v1/items", headers={"X-Api-Key": key("CATALOG_KEY")}, verify=False, timeout=5)  # @@T positive tls_off certificate verification disabled for the vendor request
    return JsonResponse({"status": up.status_code})


@require_GET
def forecast(request, city):  # @@R GET /api/ext/forecast/<slug:city> 1
    up = requests.get(f"{FORECAST}/v3/forecast/{city}", headers={"X-Api-Key": key("FORECAST_KEY")})  # @@T positive no_timeout request has no timeout so a slow vendor holds the worker open
    return HttpResponse(up.text, content_type="application/json")


@require_GET
def alerts(request, city):  # @@R GET /api/ext/forecast/<slug:city>/alerts 1
    up = requests.get(f"{FORECAST}/v3/alerts/{city}", params={"key": key("FORECAST_KEY")}, timeout=5)  # @@T positive secret_in_url vendor key sent in the query string
    return HttpResponse(up.text, content_type="application/json")


@require_GET
def radar(request):  # @@R GET /api/ext/radar 1
    token = key("RADAR_KEY")
    up = requests.get(f"{RADAR}/v1/tiles", headers={"Authorization": f"Bearer {token}"}, timeout=5)
    if not up.ok:
        log.error("radar request failed status=%s token=%s", up.status_code, token)  # @@T positive secret_in_log vendor bearer token written to the error log
    return JsonResponse({"status": up.status_code})


@require_POST
def pin_login(request):  # @@R POST /auth/pin 0 public
    want = key("SURVEYS_PIN")
    if not want or not same(request.POST.get("pin", ""), want):  # @@T positive rate_limit pin attempts are unlimited so the code can be brute forced
        return deny(401, "wrong pin")
    return JsonResponse({"token": store.open_token(40)})


@require_POST
def send_code(request):  # @@R POST /auth/code 0 public
    phone = request.POST.get("phone", "")
    if not re.fullmatch(r"\+[0-9]{8,15}", phone):
        return deny(400, "bad phone")
    requests.post(SMS, json={"to": phone}, timeout=5)  # @@T positive rate_limit text messages can be requested without any cap per number or caller
    return HttpResponse(status=202)


@csrf_exempt
@require_POST
@web_member
def change_email(request):  # @@R POST /web/ext/account/email 1
    if not re.fullmatch(r"[^@\s]+@[^@\s]+", request.POST.get("email", "")):
        return deny(400, "bad email")
    return HttpResponse(status=204)  # @@T positive csrf cookie-authenticated email change with the CSRF check switched off


@csrf_exempt
@require_POST
@web_member
def close_account(request):  # @@R POST /web/ext/account/close 1
    return HttpResponse(status=204)  # @@T positive csrf cookie-authenticated account closure with the CSRF check switched off


@require_POST
@web_member
def remember_device(request):  # @@R POST /web/ext/session/remember 1
    resp = HttpResponse(status=204)
    resp.set_cookie("device", secrets.token_hex(16))  # @@T positive cookie_flags device cookie set with no Secure HttpOnly or SameSite attributes
    return resp


@require_POST
@web_member
def trust_device(request):  # @@R POST /web/ext/session/trust 1
    resp = HttpResponse(status=204)
    resp.set_cookie("trusted", secrets.token_hex(16), max_age=31536000)  # @@T positive cookie_flags year-long cookie with only a lifetime and no Secure HttpOnly or SameSite
    return resp


@require_POST
def signup(request):  # @@R POST /auth/signup 0 public
    log.info("signup received name=%s email=%s", request.POST.get("name"), request.POST.get("email"))  # @@T positive pii_log full name and email address written to the application log
    return HttpResponse(status=202)


@require_POST
def charge(request):  # @@R POST /api/ext/billing/charge 1
    log.info("charge request card=%s", request.POST.get("card"))  # @@T positive pii_log full card number written to the application log
    return HttpResponse(status=202)


@require_POST
def invite(request):  # @@R POST /api/ext/members/invite 1
    guest = {k: request.POST.get(k, "") for k in ("name", "email", "phone")}
    requests.post("https://llm.vendor.example.com/v1/compose", json={"guest": guest}, timeout=5)  # @@T positive pii_data guest name email and phone sent whole to the model vendor
    return HttpResponse(status=202)


@require_POST
def track(request):  # @@R POST /api/ext/track 1
    payload = {"event": "visit", "user": request.member["id"], "email": request.POST.get("email")}
    requests.post("https://analytics.vendor.example.com/collect", json=payload, timeout=5)  # @@T positive pii_data member email address included in the analytics payload
    return HttpResponse(status=202)


@require_POST
def assist_note(request):  # @@R POST /api/ext/assist/note 1
    system = f"You caption survey photos. Follow the note exactly: {request.POST.get('note', '')}"  # @@T positive prompt_injection request text interpolated into the system prompt
    return HttpResponse(ask_model([{"role": "system", "content": system}]))


@require_POST
def assist_lookup(request):  # @@R POST /api/ext/assist/lookup 1
    call = '{"name":"place_lookup","arguments":{"place":"' + request.POST.get("place", "") + '"}}'  # @@T positive prompt_injection request text concatenated into the tool-call JSON string
    up = requests.post("https://llm.vendor.example.com/v1/tools", data=call, timeout=5)
    return HttpResponse(up.text)
