import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Invoice

ACCEPTED = ("customer_id", "amount", "currency", "due_date")


@csrf_exempt
@require_POST
def create_invoice(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "login required"}, status=401)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"error": "bad json"}, status=400)
    values = {key: data[key] for key in ACCEPTED if key in data}
    invoice = Invoice.objects.create(**values)
    return JsonResponse({"id": invoice.pk, "status": invoice.status}, status=201)
