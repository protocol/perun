from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy.orm import Session
from deps import get_db, get_current_user, require_admin
from models import User

app = FastAPI()
router = APIRouter(prefix="/users", dependencies=[Depends(require_admin)])


@router.put("/{user_id}/role")
def set_role(user_id: int, role: str, db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    target.role = role
    db.commit()
    return {"id": target.id, "role": target.role}


@router.delete("/{user_id}")
def remove(user_id: int, db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    return {"ok": True}


@app.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id}


app.include_router(router)
