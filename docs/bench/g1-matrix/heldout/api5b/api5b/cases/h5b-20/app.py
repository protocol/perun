from flask import Flask, jsonify, request
from flask_login import login_required
from models import db, User

app = Flask(__name__)


@app.route("/v1/users/<int:uid>")
@login_required
def show(uid):
    u = db.get_or_404(User, uid)
    return jsonify(id=u.id, status=u.status)


@app.route("/users/<int:uid>/status", methods=["PUT"])
@login_required
def set_status(uid):
    u = db.get_or_404(User, uid)
    u.status = request.get_json()["status"]
    db.session.commit()
    return jsonify(id=u.id, status=u.status)
