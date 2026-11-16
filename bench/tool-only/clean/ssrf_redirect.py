from urllib.parse import urljoin, urlparse

import requests
from flask import Flask, abort, request

app = Flask(__name__)
ALLOWED_HOSTS = {'api.example.com'}


def allowed(url):
    return urlparse(url).hostname in ALLOWED_HOSTS


@app.route('/proxy')
def proxy():
    url = request.args['url']
    if not allowed(url):
        abort(400)
    resp = requests.get(url, timeout=5, allow_redirects=False)
    if resp.is_redirect and not allowed(urljoin(url, resp.headers.get('Location', ''))):
        abort(400)
    return resp.text
