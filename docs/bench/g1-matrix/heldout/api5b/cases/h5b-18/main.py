from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session
from deps import get_db, get_current_user
from models import User

app = FastAPI()


@app.patch("/users/{user_id}/ban")
def ban_user(
    user_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404)
    target.banned = True
    db.commit()
    return {"id": target.id, "banned": True}


@app.get("/users/me")
def whoami(me: User = Depends(get_current_user)):
    return {"id": me.id}
