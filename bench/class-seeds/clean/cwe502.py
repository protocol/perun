import json
from flask import Flask, request

app = Flask(__name__)


@app.route("/restore", methods=["POST"])
def restore():
    state = json.loads(request.get_data())
    return {"keys": list(state)}
