from flask import Blueprint, request, abort, g, jsonify
from store import settings_table

admin_bp = Blueprint("admin_bp", __name__, url_prefix="/admin")


@admin_bp.before_request
def need_login():
    if getattr(g, "user", None) is None:
        abort(401)


@admin_bp.route("/settings", methods=["POST"])
def update_settings():
    for key, value in request.get_json().items():
        settings_table[key] = value
    return jsonify(settings_table)


@admin_bp.route("/settings")
def read_settings():
    return jsonify(settings_table)
