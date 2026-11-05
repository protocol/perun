from typing import Annotated
from fastapi import APIRouter, Depends
from sqlmodel import Session
from deps import get_session, get_current_user
from models import User, PermissionGrant

CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[Session, Depends(get_session)]
router = APIRouter(tags=["access"])


@router.get("/permissions")
def mine(user: CurrentUser, session: SessionDep):
    return session.query(PermissionGrant).filter_by(user_id=user.id).all()


@router.post("/permissions/grant")
def grant(user_id: int, name: str, user: CurrentUser, session: SessionDep):
    session.add(PermissionGrant(user_id=user_id, name=name))
    session.commit()
    return {"granted": name}
