from django.http import JsonResponse

from .decorators import session_for


class ApiGateMiddleware:
    # Global gate: every /api/ view needs a session unless it is marked auth_exempt.
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.path.startswith("/api/"):
            return None
        if getattr(view_func, "auth_exempt", False):
            return None
        user = session_for(request)
        if user is None:
            return JsonResponse({"error": "unauthenticated"}, status=401)
        request.user_info = user
        return None
