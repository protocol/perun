from flask import Flask, request, session

app = Flask(__name__)
app.secret_key = "example-not-real"


@app.route("/email", methods=["POST"])
def change_email():
    uid = session["user_id"]
    update_email(uid, request.form["email"])
    return "ok"
