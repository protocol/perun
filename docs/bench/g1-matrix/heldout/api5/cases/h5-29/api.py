from functools import wraps
from flask import Flask, request, jsonify, g
from auth import decode_token
from models import Grant, db

app = Flask(__name__)


def token_required(fn):
    @wraps(fn)
    def inner(*a, **kw):
        g.user = decode_token(request.headers.get("X-Token"))
        if g.user is None:
            return jsonify(error="auth"), 401
        return fn(*a, **kw)
    return inner


@app.put("/users/<int:uid>/permissions")
@token_required
def set_permissions(uid):
    Grant.query.filter_by(user_id=uid).delete()
    for name in request.json["names"]:
        db.session.add(Grant(user_id=uid, name=name))
    db.session.commit()
    return jsonify(ok=True)
