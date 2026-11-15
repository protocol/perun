from flask import Flask, request, send_from_directory

app = Flask(__name__)


@app.route("/download")
def download():
    return send_from_directory("/srv/files", request.args["name"])
