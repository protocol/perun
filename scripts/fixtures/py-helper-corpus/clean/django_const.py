import requests
from django.http import HttpResponse

def fetch_remote(url):
    return requests.get(url, timeout=5).text

def status(request):
    return HttpResponse(fetch_remote("https://status.example.com/api"))
