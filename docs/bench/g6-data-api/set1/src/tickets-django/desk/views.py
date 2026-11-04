import logging
import os
from urllib.parse import urlparse

import requests
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .decorators import auth_exempt, role_required, staff_required
from .store import QUEUES, TICKETS

log = logging.getLogger("desk")

SLA_BASE = "https://sla.vendor.example.com"
SLA_KEY = os.environ["SLA_KEY"]
PREVIEW_HOSTS = {"docs.example.com", "files.example.com"}


@auth_exempt
@require_http_methods(["GET"])
def queue_stats(request):  # @@R GET /api/public/queues 0 ; T positive missing_authn view marked auth_exempt although it returns ticket titles and owner ids
    rows = []
    for ticket in TICKETS.values():
        rows.append({"title": ticket["title"], "owner_id": ticket["owner_id"]})
    return JsonResponse({"tickets": rows})


@require_http_methods(["GET"])
def list_tickets(request):  # @@R GET /api/tickets 1
    mine = [t for t in TICKETS.values() if t["owner_id"] == request.user_info["id"]]
    return JsonResponse({"tickets": mine})


@require_http_methods(["GET"])
def get_ticket(request, ticket_id):  # @@R GET /api/tickets/<int:ticket_id> 1 ; T decoy missing_object_check middleware gate plus owner comparison
    ticket = TICKETS.get(ticket_id)
    if ticket is None or ticket["owner_id"] != request.user_info["id"]:
        return JsonResponse({"error": "not found"}, status=404)
    return JsonResponse(ticket)


@require_http_methods(["GET"])
def ticket_body(request, ticket_id):  # @@R GET /api/tickets/<int:ticket_id>/body 0 ; T positive missing_object_check any logged-in user reads any ticket body
    ticket = TICKETS.get(ticket_id)
    if ticket is None:
        return JsonResponse({"error": "not found"}, status=404)
    return JsonResponse({"id": ticket["id"], "body": ticket["body"]})


@require_http_methods(["POST"])
def sla_refresh(request):  # @@R POST /api/sla/refresh 1
    resp = requests.get(
        SLA_BASE + "/v1/targets",
        headers={"X-Api-Key": SLA_KEY},
        timeout=5,
        verify=False,  # @@T positive tls_off certificate verification disabled
    )
    return JsonResponse(resp.json())


@require_http_methods(["GET"])
def queue_count(request):  # @@R GET /api/queues/count 1
    paused = [q for q in QUEUES.values() if q["paused"]]
    return JsonResponse({"queues": len(QUEUES), "paused": len(paused)})


@require_http_methods(["POST"])
def delete_ticket(request, ticket_id):  # @@R POST /api/tickets/<int:ticket_id>/delete 1 ; T decoy missing_object_check delete limited to the owner
    ticket = TICKETS.get(ticket_id)
    if ticket is None or ticket["owner_id"] != request.user_info["id"]:
        return JsonResponse({"error": "not found"}, status=404)
    del TICKETS[ticket_id]
    return JsonResponse({}, status=204)


@require_http_methods(["POST"])
def retitle_ticket(request, ticket_id):  # @@R POST /api/tickets/<int:ticket_id>/title 0 ; T positive missing_object_check retitle without checking the ticket belongs to the caller
    ticket = TICKETS.get(ticket_id)
    if ticket is None:
        return JsonResponse({"error": "not found"}, status=404)
    ticket["title"] = request.POST.get("title", ticket["title"])
    return JsonResponse(ticket)


@require_http_methods(["GET"])
def preview(request):  # @@R GET /api/preview 1
    target = request.GET.get("url", "")
    resp = requests.get(target, timeout=5)  # @@T positive ssrf caller-controlled URL fetched server side
    return JsonResponse({"type": resp.headers.get("content-type"), "bytes": len(resp.content)})


@require_http_methods(["GET"])
def preview_safe(request):  # @@R GET /api/preview/safe 1
    target = urlparse(request.GET.get("url", ""))
    if target.scheme != "https" or target.hostname not in PREVIEW_HOSTS:
        return JsonResponse({"error": "host not allowed"}, status=400)
    resp = requests.get(target.geturl(), timeout=5, allow_redirects=False)  # @@T decoy ssrf https plus host allowlist plus no redirects
    return JsonResponse({"type": resp.headers.get("content-type")})


@require_http_methods(["GET"])
def sla_lookup(request, ticket_id):  # @@R GET /api/sla/<int:ticket_id> 1
    if ticket_id not in TICKETS:
        return JsonResponse({"error": "not found"}, status=404)
    resp = requests.get(SLA_BASE + f"/v1/tickets/{ticket_id}", headers={"X-Api-Key": SLA_KEY})  # @@T positive no_timeout outbound call without a timeout
    return JsonResponse(resp.json())


@require_http_methods(["GET"])
def sla_history(request, ticket_id):  # @@R GET /api/sla/<int:ticket_id>/history 1
    if ticket_id not in TICKETS:
        return JsonResponse({"error": "not found"}, status=404)
    resp = requests.get(SLA_BASE + f"/v1/tickets/{ticket_id}/history", headers={"X-Api-Key": SLA_KEY}, timeout=5)  # @@T decoy secret_in_url key sent in a header, with timeout
    return JsonResponse(resp.json())


@require_http_methods(["GET"])
def sla_archive(request, ticket_id):  # @@R GET /api/sla/<int:ticket_id>/archive 1
    if ticket_id not in TICKETS:
        return JsonResponse({"error": "not found"}, status=404)
    url = SLA_BASE + f"/v1/tickets/{ticket_id}/archive?key={SLA_KEY}"  # @@T positive secret_in_url API key in the query string
    resp = requests.get(url, timeout=5)
    return JsonResponse(resp.json())


@require_http_methods(["GET"])
def sla_digest(request, ticket_id):  # @@R GET /api/sla/<int:ticket_id>/digest 1
    if ticket_id not in TICKETS:
        return JsonResponse({"error": "not found"}, status=404)
    log.info("digest call using key %s", SLA_KEY)  # @@T positive secret_in_log key written to the log
    resp = requests.get(SLA_BASE + f"/v1/tickets/{ticket_id}/digest", headers={"X-Api-Key": SLA_KEY}, timeout=5)
    return JsonResponse(resp.json())


@require_http_methods(["GET"])
def sla_trend(request, ticket_id):  # @@R GET /api/sla/<int:ticket_id>/trend 1
    if ticket_id not in TICKETS:
        return JsonResponse({"error": "not found"}, status=404)
    resp = requests.get(SLA_BASE + f"/v1/tickets/{ticket_id}/trend", headers={"X-Api-Key": SLA_KEY}, timeout=5)
    log.info("trend call ok ticket=%s status=%s", ticket_id, resp.status_code)  # @@T decoy secret_in_log log line carries no secret
    return JsonResponse(resp.json())


@require_http_methods(["GET"])
def ticket_count(request):  # @@R GET /api/tickets/count 1
    mine = [t for t in TICKETS.values() if t["owner_id"] == request.user_info["id"]]
    open_ = [t for t in mine if t["status"] == "open"]
    return JsonResponse({"total": len(mine), "open": len(open_)})


# Staff views sit outside /api and use per-view decorators instead of the gate.
@require_http_methods(["GET"])
def staff_audit(request):  # @@R GET /staff/audit 0 ; T positive missing_authn staff audit trail with no decorator and outside the gate
    rows = [{"id": t["id"], "owner_id": t["owner_id"]} for t in TICKETS.values()]
    return JsonResponse({"rows": rows})


@staff_required
@require_http_methods(["POST"])
def pause_queue(request, queue_id):  # @@R POST /staff/queues/<int:queue_id>/pause 0 ; T positive missing_authz login required but any agent can pause a queue
    queue = QUEUES.get(queue_id)
    if queue is None:
        return JsonResponse({"error": "not found"}, status=404)
    queue["paused"] = True
    return JsonResponse(queue)


@role_required("lead")
@require_http_methods(["GET"])
def staff_overview(request):  # @@R GET /staff/overview 1 ; T decoy missing_authz lead role enforced by decorator
    return JsonResponse({"tickets": len(TICKETS), "queues": len(QUEUES)})


@role_required("lead")
@require_http_methods(["POST"])
def staff_reindex(request):  # @@R POST /staff/reindex 1 ; T decoy missing_authz lead role enforced by decorator
    count = len(TICKETS) + len(QUEUES)
    return JsonResponse({"queued": count}, status=202)


@staff_required
@require_http_methods(["GET"])
def my_tickets(request):  # @@R GET /staff/me/tickets 1 ; T decoy missing_authn staff_required decorator, results limited to the caller
    mine = [t for t in TICKETS.values() if t["owner_id"] == request.user_info["id"]]
    return JsonResponse({"tickets": mine})
