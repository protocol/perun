from urllib.parse import urlparse

import requests
from flask import Flask, abort, request

app = Flask(__name__)
ALLOWED_HOSTS = {'api.example.com'}


@app.route('/proxy')
def proxy():
    url = request.args['url']
    if urlparse(url).hostname not in ALLOWED_HOSTS:
        abort(400)
    return requests.get(url, timeout=5).text
