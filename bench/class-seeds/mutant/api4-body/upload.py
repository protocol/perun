from flask import Flask, request, jsonify

app = Flask(__name__)


@app.post("/import")
def import_blob():
    raw = request.get_data()
    return jsonify(size=len(raw))
