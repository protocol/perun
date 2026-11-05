from functools import wraps
from flask import Flask, jsonify, abort
from flask_login import login_required, current_user
from models import db, User

app = Flask(__name__)


def admin_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if getattr(current_user, "role", None) != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return inner


@app.route("/admin/users/export")
@login_required
@admin_required
def export_users():
    rows = User.query.order_by(User.id).all()
    return jsonify([{"id": u.id, "email": u.email} for u in rows])


@app.route("/v1/profile")
@login_required
def profile():
    return jsonify(id=current_user.id)
