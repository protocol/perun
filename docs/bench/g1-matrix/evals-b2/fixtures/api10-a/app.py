from flask import Flask, jsonify, request, abort
from report import build

app = Flask(__name__)

@app.get("/report")
def report():
    country = request.args.get("country", "")
    if len(country) != 2 or not country.isalpha():
        abort(400)
    return jsonify(build(country.upper()))
