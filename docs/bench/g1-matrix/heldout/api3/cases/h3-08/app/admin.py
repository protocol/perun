from functools import wraps

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from .extensions import db
from .models import User

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)

    return wrapper


@bp.route("/users", methods=["POST"])
@login_required
@admin_required
def create_user():
    user = User(**request.get_json())
    db.session.add(user)
    db.session.commit()
    return jsonify({"id": user.id, "email": user.email}), 201
