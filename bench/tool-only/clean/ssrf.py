import requests
from flask import Flask, request, abort

app = Flask(__name__)
ALLOWED = {'https://api.example.com/status'}


@app.route('/fetch')
def fetch():
    url = request.args['url']
    if url not in ALLOWED:
        abort(400)
    return requests.get(url, timeout=5).text
