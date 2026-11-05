from flask import Blueprint, request, abort, g, jsonify
from store import settings_table

ALLOWED_GROUPS = {"ops", "root"}
admin_bp = Blueprint("admin_bp", __name__, url_prefix="/admin")


@admin_bp.before_request
def gate():
    user = getattr(g, "user", None)
    if user is None:
        abort(401)
    if user.group not in ALLOWED_GROUPS:
        abort(403)


@admin_bp.route("/settings", methods=["POST"])
def update_settings():
    for key, value in request.get_json().items():
        settings_table[key] = value
    return jsonify(settings_table)


@admin_bp.route("/settings")
def read_settings():
    return jsonify(settings_table)
