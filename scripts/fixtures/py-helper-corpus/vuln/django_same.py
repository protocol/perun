import requests
from django.http import HttpResponse

def fetch_remote(url):
    return requests.get(url, timeout=5).text  # SINK ssrf

def proxy(request):
    return HttpResponse(fetch_remote(request.GET.get("url")))

def banner(name):
    return HttpResponse(f"<h1>Hello {name}</h1>")  # SINK xss

def hello(request):
    return banner(request.GET.get("name"))
