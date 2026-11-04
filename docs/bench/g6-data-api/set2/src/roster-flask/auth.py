import secrets
from functools import wraps

from flask import abort, g, request

SESSIONS = {}


def open_session(user_id, role):
    token = secrets.token_hex(24)
    SESSIONS[token] = {"user_id": user_id, "role": role, "csrf": secrets.token_hex(16)}
    return token


def bearer_session():
    return SESSIONS.get(request.headers.get("Authorization", "").removeprefix("Bearer "))


def need_login(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        sess = bearer_session()
        if sess is None:
            abort(401)
        g.user = sess
        return view(*args, **kwargs)

    return wrapper


def need_role(role):
    def deco(view):
        @wraps(view)
        @need_login
        def wrapper(*args, **kwargs):
            if g.user["role"] != role:
                abort(403)
            return view(*args, **kwargs)

        return wrapper

    return deco


def cookie_login(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        sess = SESSIONS.get(request.cookies.get("sid", ""))
        if sess is None:
            abort(401)
        g.user = sess
        return view(*args, **kwargs)

    return wrapper
