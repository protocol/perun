"""Fictional Acme seed: CWE-200 fixed twin (public fields only, generic error)."""
from flask import Flask, jsonify

app = Flask(__name__)
USERS = {1: {"name": "Jane Smith", "email": "jane@example.com", "password_hash": "x1", "api_key": "k-demo"}}


@app.route("/users/<int:uid>")
def get_user(uid):
    user = USERS.get(uid)
    if user is None:
        return jsonify(error="not found"), 404
    return jsonify(name=user["name"])
