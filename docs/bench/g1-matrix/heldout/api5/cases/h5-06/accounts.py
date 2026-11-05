from flask import Flask, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import select
from db import Session, Account

app = Flask(__name__)


@app.get("/accounts/me")
@login_required
def me():
    with Session() as s:
        acct = s.scalar(select(Account).where(Account.id == current_user.id))
        return jsonify(email=acct.email)


@app.patch("/accounts/<int:account_id>/email")
@login_required
def change_email(account_id):
    with Session() as s:
        acct = s.get(Account, account_id)
        acct.email = request.json["email"]
        s.commit()
        return jsonify(email=acct.email)
