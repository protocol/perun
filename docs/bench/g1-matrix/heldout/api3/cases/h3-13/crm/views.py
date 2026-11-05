import json

from django.http import Http404, JsonResponse
from django.views.decorators.http import require_http_methods

from .models import Customer


@require_http_methods(["PATCH"])
def update_customer(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "login required"}, status=401)
    data = json.loads(request.body or "{}")
    rows = Customer.objects.filter(pk=pk, owner=request.user).update(**data)
    if rows == 0:
        raise Http404("customer not found")
    customer = Customer.objects.get(pk=pk)
    return JsonResponse({"id": customer.pk, "name": customer.name})
