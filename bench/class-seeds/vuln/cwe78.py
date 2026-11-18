from flask import Flask, request
import os

app = Flask(__name__)


@app.route("/lookup")
def lookup():
    zone = request.args.get("zone")
    return os.system("dig +short acme.example.com " + zone)
