from flask import Blueprint, jsonify, request, abort
from flask_login import current_user
from models import db, Setting

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
def must_be_signed_in():
    if not current_user.is_authenticated:
        abort(401)


@admin_bp.route("/settings/<key>", methods=["PUT"])
def update_setting(key):
    row = Setting.query.filter_by(key=key).first_or_404()
    row.value = request.get_json()["value"]
    db.session.commit()
    return jsonify(key=row.key, value=row.value)
