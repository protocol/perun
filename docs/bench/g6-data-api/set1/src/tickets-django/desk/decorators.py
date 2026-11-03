from functools import wraps

from django.http import JsonResponse

from .store import TOKENS


def session_for(request):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    return TOKENS.get(token)


def auth_exempt(view):
    # Marks a view the global middleware must not gate.
    view.auth_exempt = True
    return view


def staff_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = session_for(request)
        if user is None:
            return JsonResponse({"error": "unauthenticated"}, status=401)
        request.user_info = user
        return view(request, *args, **kwargs)

    return wrapper


def role_required(role):
    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = session_for(request)
            if user is None:
                return JsonResponse({"error": "unauthenticated"}, status=401)
            if user["role"] != role:
                return JsonResponse({"error": "forbidden"}, status=403)
            request.user_info = user
            return view(request, *args, **kwargs)

        return wrapper

    return deco
