from functools import wraps

from django.http import JsonResponse

from . import store

GATED = ("/api/", "/admin-api/")
PUBLIC_PREFIXES = ("/api/public/", "/api/exports/")


def deny(status, error):
    return JsonResponse({"error": error}, status=status)


class TokenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith(GATED) and not path.startswith(PUBLIC_PREFIXES):
            member = store.member_for(request.headers.get("Authorization", ""))
            if member is None:
                return deny(401, "sign in first")
            request.member = member
            request._dont_enforce_csrf_checks = True
        return self.get_response(request)


def require_role(role):
    def wrap(view):
        @wraps(view)
        def inner(request, *args, **kwargs):
            if request.member["role"] != role:
                return deny(403, "forbidden")
            return view(request, *args, **kwargs)
        return inner
    return wrap


def web_member(view):
    @wraps(view)
    def inner(request, *args, **kwargs):
        uid = request.session.get("uid")
        if uid not in store.USERS:
            return deny(401, "sign in first")
        request.member = store.USERS[uid]
        return view(request, *args, **kwargs)
    return inner
