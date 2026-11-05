from flask import Blueprint, jsonify, request

from .extensions import db
from .models import User

bp = Blueprint("users", __name__)


@bp.route("/users", methods=["POST"])
def create_user():
    payload = request.get_json(silent=True)
    if not payload or "email" not in payload:
        return jsonify({"error": "email required"}), 400
    if User.query.filter_by(email=payload["email"]).first():
        return jsonify({"error": "exists"}), 409
    user = User(**request.get_json())
    db.session.add(user)
    db.session.commit()
    return jsonify({"id": user.id, "email": user.email}), 201
