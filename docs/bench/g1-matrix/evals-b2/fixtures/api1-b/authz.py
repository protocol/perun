from functools import wraps
from flask import request, g, abort

TOKENS = {"t-ana": "ana", "t-ben": "ben"}

def login_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        user = TOKENS.get(request.headers.get("X-Token", ""))
        if user is None:
            abort(401)
        g.user = user
        return fn(*args, **kwargs)
    return inner

def can_read(user, doc):
    return doc is not None and (doc.owner == user or user in doc.shared_with)

def can_write(user, doc):
    return doc is not None and doc.owner == user
