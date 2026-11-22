from flask import Flask, request
import subprocess

app = Flask(__name__)


@app.route("/lookup")
def lookup():
    zone = request.args.get("zone")
    return subprocess.run(["dig", "+short", "acme.example.com", zone], capture_output=True, text=True).stdout
