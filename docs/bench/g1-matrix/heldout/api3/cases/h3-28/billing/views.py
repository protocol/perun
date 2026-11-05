import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Invoice


@csrf_exempt
@require_POST
def create_invoice(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "login required"}, status=401)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"error": "bad json"}, status=400)
    if "customer_id" not in data:
        return JsonResponse({"error": "customer_id required"}, status=400)
    invoice = Invoice.objects.create(**data)
    return JsonResponse({"id": invoice.pk, "status": invoice.status}, status=201)
