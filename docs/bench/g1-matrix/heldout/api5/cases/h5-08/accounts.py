from flask import Flask, request, jsonify, abort
from flask_login import login_required, current_user
from db import Session, Account

app = Flask(__name__)


@app.get("/accounts/me")
@login_required
def me():
    with Session() as s:
        return jsonify(email=s.get(Account, current_user.id).email)


@app.patch("/accounts/<int:account_id>/email")
@login_required
def change_email(account_id):
    if account_id != current_user.id and not current_user.is_staff:
        abort(403)
    with Session() as s:
        acct = s.get(Account, account_id)
        acct.email = request.json["email"]
        s.commit()
        return jsonify(email=acct.email)
