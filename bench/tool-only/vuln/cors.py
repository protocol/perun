from flask import Flask, request

app = Flask(__name__)


@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin')
    resp.headers['Access-Control-Allow-Credentials'] = 'true'
    return resp
