from functools import wraps
from flask import request, g, abort
from store import TOKENS, ROLES

def authenticated(fn):
    @wraps(fn)
    def inner(*a, **kw):
        name = TOKENS.get(request.headers.get("X-Token", ""))
        if not name:
            abort(401)
        g.user, g.role = name, ROLES[name]
        return fn(*a, **kw)
    return inner

def may_view(ticket):
    return ticket is not None and (g.role == "agent" or ticket["reporter"] == g.user)

def require_agent():
    if g.role != "agent":
        abort(403)
