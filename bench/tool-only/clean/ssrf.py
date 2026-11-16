import requests
from flask import Flask, abort, request

app = Flask(__name__)
TARGETS = {'status': 'https://api.example.com/status'}


@app.route('/fetch')
def fetch():
    url = TARGETS.get(request.args.get('t', ''))
    if url is None:
        abort(400)
    resp = requests.get(url, timeout=5)
    return resp.text
