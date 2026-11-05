from flask import Flask, jsonify, request, abort
from flask_login import login_required, current_user
from models import db, User

app = Flask(__name__)


@app.route("/v1/me")
@login_required
def me():
    return jsonify(id=current_user.id, name=current_user.display_name)


@app.route("/users/<int:uid>/display-name", methods=["PUT"])
@login_required
def rename(uid):
    if uid != current_user.id:
        abort(403)
    current_user.display_name = request.get_json()["name"][:60]
    db.session.commit()
    return jsonify(id=uid, name=current_user.display_name)
