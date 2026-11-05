from flask import Blueprint, jsonify, request
from marshmallow import EXCLUDE, Schema, fields

from .extensions import db
from .models import User

bp = Blueprint("users", __name__)


class SignupSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    email = fields.Email(required=True)
    name = fields.Str(required=True)
    is_admin = fields.Bool(dump_only=True)


@bp.route("/users", methods=["POST"])
def create_user():
    data = SignupSchema().load(request.get_json(silent=True) or {})
    user = User(**data)
    db.session.add(user)
    db.session.commit()
    return jsonify({"id": user.id, "email": user.email}), 201
