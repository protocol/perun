from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from extensions import db
from models import Member

bp = Blueprint("members", __name__)


@bp.route("/members/<int:member_id>/promote", methods=["POST"])
@jwt_required()
def promote(member_id):
    member = Member.query.get_or_404(member_id)
    member.role = request.json.get("role", "editor")
    db.session.commit()
    return jsonify(id=member.id, role=member.role)


@bp.route("/members")
@jwt_required()
def listing():
    return jsonify([m.id for m in Member.query.all()])
