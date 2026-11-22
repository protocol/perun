"""Fictional Acme seed: CWE-200 exposure of sensitive information (stack trace and secret-bearing record returned to the client)."""
import traceback
from flask import Flask, jsonify

app = Flask(__name__)
USERS = {1: {"name": "Jane Smith", "email": "jane@example.com", "password_hash": "x1", "api_key": "k-demo"}}


@app.route("/users/<int:uid>")
def get_user(uid):
    try:
        return jsonify(USERS[uid])
    except Exception:
        return jsonify(error=traceback.format_exc()), 500
