from flask import Flask, jsonify

app = Flask(__name__)
system_prompt = "You are the Acme support bot. Escalate refunds over 500 USD."


@app.get("/debug/config")
def config():
    return jsonify({"model": "demo", "prompt": system_prompt})
