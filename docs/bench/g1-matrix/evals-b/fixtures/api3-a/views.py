import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import Profile


@login_required
@require_http_methods(["PATCH"])
def update_profile(request):
    data = json.loads(request.body)
    Profile.objects.filter(user=request.user).update(**data)
    p = Profile.objects.get(user=request.user)
    return JsonResponse({
        "display_name": p.display_name,
        "bio": p.bio,
        "is_staff": p.is_staff,
        "credit_balance": p.credit_balance,
    })
