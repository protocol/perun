from fastapi import Depends, Header, HTTPException, Request

from app.store import SESSIONS, USERS


def current_user(authorization: str = Header(default="")):
    sess = SESSIONS.get(authorization.removeprefix("Bearer "))
    if sess is None:
        raise HTTPException(401)
    return sess


def require_admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
    return user


def cookie_user(request: Request):
    sess = SESSIONS.get(request.cookies.get("sid", ""))
    if sess is None:
        raise HTTPException(401)
    return sess


def member(request: Request):
    uid = request.session.get("uid")
    if uid not in USERS:
        raise HTTPException(401)
    return USERS[uid]
