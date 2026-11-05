from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from deps import get_db, get_current_user
from models import User

router = APIRouter()


class RoleIn(BaseModel):
    role: str


@router.put("/users/{user_id}/role")
def set_role(user_id: int, body: RoleIn, current_user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    target.role = body.role
    db.commit()
    return {"id": target.id, "role": target.role}
