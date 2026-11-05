from functools import wraps
from flask import request, jsonify, g
from auth import decode_token, scopes_for


def token_required(fn):
    @wraps(fn)
    def inner(*a, **kw):
        g.user = decode_token(request.headers.get("X-Token"))
        if g.user is None:
            return jsonify(error="auth"), 401
        return fn(*a, **kw)
    return inner


def permission_required(name):
    def deco(fn):
        @wraps(fn)
        def inner(*a, **kw):
            if name not in scopes_for(g.user):
                return jsonify(error="denied"), 403
            return fn(*a, **kw)
        return inner
    return deco
