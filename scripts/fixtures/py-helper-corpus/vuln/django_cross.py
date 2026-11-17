from django.http import HttpResponse
from helpers_c import search, load_cfg, bounce

def s(request):
    return HttpResponse(str(search(request.GET.get("q"))))

def cfg(request):
    return HttpResponse(str(load_cfg(request.body)))

def b(request):
    return bounce(request.GET.get("next"))
