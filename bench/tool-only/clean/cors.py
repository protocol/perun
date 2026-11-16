from flask import Flask, request

app = Flask(__name__)
ALLOWED_ORIGINS = {'https://app.example.com': 'app', 'https://admin.example.com': 'admin'}
ORIGIN_FOR = {'app': 'https://app.example.com', 'admin': 'https://admin.example.com'}


@app.after_request
def add_cors(resp):
    origin = ORIGIN_FOR.get(ALLOWED_ORIGINS.get(request.headers.get('Origin')))
    if origin:
        resp.headers['Access-Control-Allow-Origin'] = origin
        resp.headers['Access-Control-Allow-Credentials'] = 'true'
    return resp
