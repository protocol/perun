from fastapi import APIRouter, Depends, HTTPException

from .auth import current_user
from .db import get_db

router = APIRouter()


def require_admin(user=Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    return user


@router.get("/users/me")
def me(user=Depends(current_user)):
    return {"id": user.id, "email": user.email}


@router.post("/users/{user_id}/suspend", status_code=204)
def suspend(user_id: int, _=Depends(require_admin), db=Depends(get_db)):
    db.execute("UPDATE users SET suspended = 1 WHERE id = ?", (user_id,))
    db.commit()
