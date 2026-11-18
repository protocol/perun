from flask import Flask, request
import os

app = Flask(__name__)


def build(zone):
    return f"nslookup {zone} 192.0.2.1"


@app.post("/lookup")
def lookup():
    zone = request.form["zone"]
    return os.popen(build(zone)).read()
