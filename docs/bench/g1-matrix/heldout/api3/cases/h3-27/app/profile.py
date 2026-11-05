from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from .extensions import db

bp = Blueprint("profile", __name__)


@bp.route("/profile", methods=["PUT"])
@login_required
def update_profile():
    user = current_user
    body = request.get_json() or {}
    for key, value in body.items():
        setattr(user, key, value)
    db.session.commit()
    return jsonify({"id": user.id, "name": user.name, "email": user.email})


@bp.route("/profile", methods=["GET"])
@login_required
def read_profile():
    return jsonify({"id": current_user.id, "name": current_user.name})
