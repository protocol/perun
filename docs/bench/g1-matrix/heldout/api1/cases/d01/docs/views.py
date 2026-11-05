from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse

from .models import Document


@login_required
def my_documents(request):
    rows = Document.objects.filter(owner=request.user).values("id", "title")
    return JsonResponse({"documents": list(rows)})


@login_required
def document_detail(request, pk):
    try:
        doc = Document.objects.get(pk=pk, owner=request.user)
    except Document.DoesNotExist:
        raise Http404
    return JsonResponse({"id": doc.pk, "title": doc.title, "body": doc.body})


@login_required
def document_share_link(request, pk):
    doc = Document.objects.get(pk=pk)
    return JsonResponse({"url": f"https://example.com/s/{doc.share_token}"})
