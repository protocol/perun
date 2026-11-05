from fastapi import Depends, HTTPException


def get_current_user():
    raise NotImplementedError


def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin required")
    return user
