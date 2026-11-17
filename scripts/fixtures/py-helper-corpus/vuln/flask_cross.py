from flask import Flask, request
from helpers_a import ping, wrap_html
app = Flask(__name__)

@app.route("/ping")
def p():
    return ping(request.args.get("host"))

@app.route("/hi")
def hi():
    return wrap_html(request.args.get("n"))
