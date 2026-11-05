from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session
from deps import get_db, get_current_user
from models import User

app = FastAPI()


@app.get("/v1/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}


@app.put("/users/{user_id}/role")
def set_role(
    user_id: int,
    role: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = db.get(User, user_id)
    target.role = role
    db.commit()
    return {"id": target.id, "role": target.role}
