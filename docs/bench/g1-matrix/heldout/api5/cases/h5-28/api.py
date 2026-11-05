from flask import Flask, request, jsonify
from guards import token_required, permission_required
from models import Grant, db

app = Flask(__name__)


@app.put("/users/<int:uid>/permissions")
@token_required
@permission_required("grants.write")
def set_permissions(uid):
    Grant.query.filter_by(user_id=uid).delete()
    for name in request.json["names"]:
        db.session.add(Grant(user_id=uid, name=name))
    db.session.commit()
    return jsonify(ok=True)
