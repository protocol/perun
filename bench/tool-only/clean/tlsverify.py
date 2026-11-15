import requests


def get_status():
    return requests.get('https://api.example.com/status', timeout=5).text
