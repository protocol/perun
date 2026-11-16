import json

from flask import Flask, request

app = Flask(__name__)


@app.route('/restore')
def restore():
    return json.loads(request.args['blob'])
