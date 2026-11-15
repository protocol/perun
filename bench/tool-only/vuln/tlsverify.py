import requests


def get_status():
    return requests.get('https://api.example.com/status', verify=False, timeout=5).text
