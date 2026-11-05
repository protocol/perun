from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404

from .models import Ticket


@login_required
def ticket_detail(request, ticket_id):
    try:
        ticket = Ticket.objects.get(pk=ticket_id, owner=request.user)
    except Ticket.DoesNotExist:
        raise Http404("no such ticket")
    return JsonResponse({
        "id": ticket.pk,
        "subject": ticket.subject,
        "status": ticket.status,
    })


@login_required
def ticket_list(request):
    rows = Ticket.objects.filter(owner=request.user).values("id", "subject")
    return JsonResponse({"tickets": list(rows)})
