import requests
from flask import Flask, request

app = Flask(__name__)


@app.route('/fetch')
def fetch():
    if request.args.get('t') == 'status':
        return requests.get('https://api.example.com/status', timeout=5).text
    return 'unknown target', 400
