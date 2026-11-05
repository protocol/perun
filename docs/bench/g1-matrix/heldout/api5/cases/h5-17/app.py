from flask import Flask, jsonify
from flask_login import login_required, current_user
from models import db, User

app = Flask(__name__)


@app.route("/profile")
@login_required
def profile():
    return jsonify(name=current_user.name)


@app.route("/admin/users/<int:user_id>", methods=["DELETE"])
@login_required
def remove_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify(error="missing"), 404
    db.session.delete(user)
    db.session.commit()
    return "", 204
