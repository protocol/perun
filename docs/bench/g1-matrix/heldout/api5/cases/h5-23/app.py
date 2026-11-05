from flask import Flask, jsonify
from flask_login import login_required, current_user
from flask_principal import Permission, RoleNeed
from models import db, User

app = Flask(__name__)
admin_permission = Permission(RoleNeed("admin"))


@app.route("/profile")
@login_required
def profile():
    return jsonify(name=current_user.name)


@app.route("/admin/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_permission.require(http_exception=403)
def remove_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify(error="missing"), 404
    db.session.delete(user)
    db.session.commit()
    return "", 204
