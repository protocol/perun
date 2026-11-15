import requests
from flask import Flask, request

app = Flask(__name__)


@app.route('/fetch')
def fetch():
    return requests.get(request.args['url'], timeout=5).text
