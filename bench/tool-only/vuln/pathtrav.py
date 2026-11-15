from flask import Flask, request, send_file

app = Flask(__name__)


@app.route("/download")
def download():
    return send_file("/srv/files/" + request.args["name"])
