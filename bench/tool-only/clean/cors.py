from flask import Flask, request

app = Flask(__name__)
ALLOWED_ORIGINS = {'https://app.example.com', 'https://admin.example.com'}


@app.after_request
def add_cors(resp):
    origin = request.headers.get('Origin')
    if origin in ALLOWED_ORIGINS:
        resp.headers['Access-Control-Allow-Origin'] = origin
        resp.headers['Access-Control-Allow-Credentials'] = 'true'
    return resp
