from flask import Flask, jsonify, request
from flask_login import login_required, current_user
from models import db, User

app = Flask(__name__)


@app.route("/v1/profile")
@login_required
def profile():
    return jsonify(id=current_user.id, email=current_user.email)


@app.route("/admin/users/<int:uid>/purge", methods=["POST"])
@login_required
def purge_user(uid):
    User.query.filter_by(id=uid).delete()
    db.session.commit()
    return "", 204
