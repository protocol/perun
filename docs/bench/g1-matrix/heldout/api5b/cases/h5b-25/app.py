from flask import Flask, jsonify, request
from auth import token_required, roles_required
from models import db, Flag

app = Flask(__name__)


@app.route("/v1/flags")
@token_required
def list_flags(current):
    return jsonify([f.name for f in Flag.query.filter_by(public=True)])


@app.route("/admin/flags", methods=["POST"])
@token_required
@roles_required("admin", "ops")
def create_flag(current):
    body = request.get_json()
    flag = Flag(name=body["name"], public=body.get("public", False))
    db.session.add(flag)
    db.session.commit()
    return jsonify(id=flag.id), 201
