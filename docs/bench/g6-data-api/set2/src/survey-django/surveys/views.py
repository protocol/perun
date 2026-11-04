import csv
import io

from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from . import store
from .access import deny, require_role


def lookup(table, key):
    row = table.get(key)
    if row is None:
        raise Http404
    return row


@require_GET
def health(request):  # @@R GET /healthz 0 public
    return JsonResponse({"ok": True})


@require_GET
def public_survey(request, sid):  # @@R GET /api/public/surveys/<int:sid> 0 public
    survey = lookup(store.SURVEYS, sid)
    if not survey["published"]:
        raise Http404
    return JsonResponse({"id": survey["id"], "title": survey["title"]})


@require_GET
def exports_csv(request):  # @@R GET /api/exports/responses.csv 0 ; T positive missing_authn exports prefix sits in the middleware public list and the view never reads a member
    out = io.StringIO()
    w = csv.writer(out)
    for r in store.RESPONSES.values():
        w.writerow([r["id"], r["survey"], r["user"], r["answer"]])
    return HttpResponse(out.getvalue(), content_type="text/csv")


@require_GET
def my_surveys(request):  # @@R GET /api/surveys/mine 1 ; T decoy missing_authn middleware gates the prefix and the view filters on the member id it set
    rows = [s for s in store.SURVEYS.values() if s["owner"] == request.member["id"]]
    return JsonResponse({"surveys": rows})


@require_GET
def survey_detail(request, sid):  # @@R GET /api/surveys/<int:sid> 1 ; T decoy missing_object_check survey owner compared with the member and a foreign id answers 404
    survey = lookup(store.SURVEYS, sid)
    if survey["owner"] != request.member["id"]:
        raise Http404
    return JsonResponse(survey)


@require_POST
def publish_survey(request, sid):  # @@R POST /api/surveys/<int:sid>/publish 0 ; T positive missing_authz publishing is an admin action but any member passes
    lookup(store.SURVEYS, sid)["published"] = True
    return JsonResponse({"ok": True})


@require_POST
@require_role("admin")
def archive_survey(request, sid):  # @@R POST /api/admin/surveys/<int:sid>/archive 1 ; T decoy missing_authz require_role admin decorator rejects every other role
    lookup(store.SURVEYS, sid)["archived"] = True
    return JsonResponse({"ok": True})


@require_POST
def purge_response(request, rid):  # @@R POST /api/admin/responses/<int:rid>/purge 1 ; T decoy missing_authz view rejects any member whose role is not admin before deleting
    if request.member["role"] != "admin":
        return deny(403, "forbidden")
    lookup(store.RESPONSES, rid)
    del store.RESPONSES[rid]
    return JsonResponse({"ok": True})


@require_POST
def close_survey(request, sid):  # @@R POST /api/surveys/<int:sid>/close 1 ; T decoy missing_object_check closing allowed for the owner or an admin and others get 404
    survey = lookup(store.SURVEYS, sid)
    if survey["owner"] != request.member["id"] and request.member["role"] != "admin":
        raise Http404
    survey["closed"] = True
    return JsonResponse({"ok": True})


@require_GET
def legacy_results(request, sid):  # @@R GET /legacy/results/<int:sid> 0 ; T positive missing_authn legacy path is outside the gated prefixes and the view never reads a member
    answers = [r["answer"] for r in store.RESPONSES.values() if r["survey"] == sid]
    return JsonResponse({"survey": sid, "answers": answers})


@require_POST
def annotate_response(request, rid):  # @@R POST /api/responses/<int:rid>/note 0 ; T positive missing_object_check note written without checking the response belongs to the member
    lookup(store.RESPONSES, rid)["note"] = request.POST.get("note", "")[:300]
    return JsonResponse({"ok": True})


@require_GET
def user_surveys(request, uid):  # @@R GET /api/users/<int:uid>/surveys 0 ; T positive missing_object_check path user id used as the filter and never compared with the member
    return JsonResponse({"surveys": [s for s in store.SURVEYS.values() if s["owner"] == uid]})
