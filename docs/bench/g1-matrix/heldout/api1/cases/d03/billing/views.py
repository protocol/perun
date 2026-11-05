from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST

from .models import Invoice


@login_required
@require_POST
def pay_invoice(request):
    invoice = Invoice.objects.filter(pk=request.POST["invoice_id"]).first()
    if invoice is None or invoice.customer_id != request.user.id:
        return HttpResponseForbidden()
    invoice.paid = True
    invoice.save()
    return JsonResponse({"paid": True})


@login_required
@require_POST
def void_invoice(request):
    invoice = Invoice.objects.filter(pk=request.POST["invoice_id"]).first()
    if invoice is None:
        return JsonResponse({"error": "missing"}, status=404)
    invoice.voided = True
    invoice.save()
    return JsonResponse({"voided": True})
