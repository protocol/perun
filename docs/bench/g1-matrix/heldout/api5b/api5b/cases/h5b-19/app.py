from flask import Flask, jsonify, request, abort
from flask_jwt_extended import JWTManager, jwt_required, get_jwt, get_jwt_identity
from models import db, User

app = Flask(__name__)
JWTManager(app)


@app.route("/v1/me")
@jwt_required()
def me():
    user = db.session.get(User, get_jwt_identity())
    return jsonify(id=user.id, email=user.email)


@app.route("/roles/grant", methods=["POST"])
@jwt_required()
def grant_role():
    if "roles:write" not in get_jwt().get("perms", []):
        abort(403)
    body = request.get_json()
    target = db.session.get(User, body["user_id"])
    target.roles = list(set(target.roles) | {body["role"]})
    db.session.commit()
    return jsonify(id=target.id, roles=target.roles)
